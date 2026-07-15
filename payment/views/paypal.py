import json
import logging

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from checkout.models import Order, OrderStatus
from payment import paypal_client
from payment.services import finalize_paid_order

logger = logging.getLogger(__name__)


def paypal_checkout(request, order_number):
    order = get_object_or_404(Order, order_number=order_number, status=OrderStatus.PENDING)
    return render(request, 'payment/paypal_checkout.html', {
        'order': order,
        'PAYPAL_CLIENT_ID': settings.PAYPAL_CLIENT_ID,
    })


@require_POST
def create_paypal_order(request, order_number):
    order = get_object_or_404(Order, order_number=order_number, status=OrderStatus.PENDING)
    try:
        paypal_order = paypal_client.create_order(order.total, order.currency, custom_id=order.order_number)
    except Exception:
        logger.exception("PayPal order creation failed for order %s", order_number)
        return JsonResponse({'error': 'Could not create PayPal order'}, status=400)
    return JsonResponse({'id': paypal_order['id']})


@require_POST
def capture_paypal_order(request, order_number):
    order = get_object_or_404(Order, order_number=order_number, status=OrderStatus.PENDING)

    try:
        data = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    paypal_order_id = data.get('paypal_order_id')
    if not paypal_order_id:
        return JsonResponse({'error': 'Missing paypal_order_id'}, status=400)

    try:
        capture = paypal_client.capture_order(paypal_order_id)
    except Exception:
        logger.exception("PayPal capture failed for order %s", order_number)
        return JsonResponse({'error': 'Could not capture PayPal order'}, status=400)

    if capture.get('status') != 'COMPLETED':
        return JsonResponse({'error': f"Payment not completed (status: {capture.get('status')})"}, status=400)

    finalize_paid_order(order, 'paypal', paypal_order_id, order.total, capture)

    redirect_url = reverse('checkout:order_confirmation', args=[order.order_number])
    return JsonResponse({'redirect_url': redirect_url})


@csrf_exempt
@require_POST
def paypal_webhook(request):
    """Async safety-net for missed client-side captures. Real security here
    comes from PayPal's verify-webhook-signature API, not CSRF (this is a
    server-to-server call, never a browser request) — every payload is
    verified against the PAYPAL-TRANSMISSION-* headers before it's trusted
    enough to call finalize_paid_order."""
    try:
        event = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    if not settings.PAYPAL_WEBHOOK_ID:
        logger.error("PAYPAL_WEBHOOK_ID is not configured; rejecting webhook.")
        return JsonResponse({'error': 'Webhook verification not configured'}, status=403)

    transmission_headers = {
        'transmission_id': request.headers.get('Paypal-Transmission-Id'),
        'transmission_time': request.headers.get('Paypal-Transmission-Time'),
        'cert_url': request.headers.get('Paypal-Cert-Url'),
        'auth_algo': request.headers.get('Paypal-Auth-Algo'),
        'transmission_sig': request.headers.get('Paypal-Transmission-Sig'),
    }
    if not all(transmission_headers.values()):
        logger.warning("PayPal webhook missing required transmission headers.")
        return JsonResponse({'error': 'Missing signature headers'}, status=400)

    try:
        verified = paypal_client.verify_webhook_signature(
            transmission_headers, event, settings.PAYPAL_WEBHOOK_ID
        )
    except Exception:
        logger.exception("PayPal webhook signature verification request failed")
        return JsonResponse({'error': 'Could not verify webhook signature'}, status=400)

    if not verified:
        logger.warning("PayPal webhook signature verification failed")
        return JsonResponse({'error': 'Invalid webhook signature'}, status=403)

    resource = event.get('resource', {})
    order_number = resource.get('purchase_units', [{}])[0].get('custom_id') or resource.get('invoice_id')
    if not order_number:
        return JsonResponse({'error': 'Missing order reference'}, status=400)

    try:
        order = Order.objects.get(order_number=order_number)
    except Order.DoesNotExist:
        return JsonResponse({'error': 'Order not found'}, status=404)

    if order.status != OrderStatus.PAID and resource.get('status') == 'COMPLETED':
        finalize_paid_order(order, 'paypal', resource.get('id', ''), order.total, event)

    return JsonResponse({'received': True})
