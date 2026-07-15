import logging

from django.conf import settings
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from mercadopago import SDK

from checkout.models import Order, OrderStatus
from payment.services import finalize_paid_order

logger = logging.getLogger(__name__)


def _absolute_url(view_name, *args):
    return f'{settings.PROTOCOL}{settings.DOMAIN}{reverse(view_name, args=args)}'


def mercadopago_checkout(request, order_number):
    """No landing template — builds a preference and redirects straight to
    MercadoPago's hosted checkout page (no MP Bricks JS embed)."""
    order = get_object_or_404(Order, order_number=order_number, status=OrderStatus.PENDING)
    sdk = SDK(settings.MERCADOPAGO_ACCESS_TOKEN)

    preference = {
        'items': [{
            'id': order.order_number,
            'title': order.items.first().item_title if order.items.exists() else order.order_number,
            'quantity': 1,
            'currency_id': order.currency,
            'unit_price': float(order.total),
        }],
        'external_reference': order.order_number,
        'back_urls': {
            'success': _absolute_url('checkout:order_confirmation', order.order_number),
            'pending': _absolute_url('checkout:order_confirmation', order.order_number),
            'failure': _absolute_url('payment:payment_failed', order.order_number),
        },
        'auto_return': 'approved',
        'notification_url': _absolute_url('payment:mercadopago_webhook'),
    }

    try:
        preference_response = sdk.preference().create(preference)
        init_point = preference_response['response']['init_point']
    except Exception:
        logger.exception("MercadoPago preference creation failed for order %s", order_number)
        return HttpResponseRedirect(reverse('payment:choose_gateway', args=[order.order_number]))

    return HttpResponseRedirect(init_point)


@csrf_exempt
@require_POST
def mercadopago_webhook(request):
    """Async notification handler — MercadoPago's flow is finalized here,
    not in a synchronous capture call. Not exercisable end-to-end without a
    live MercadoPago sandbox account."""
    payment_id = request.GET.get('data.id') or request.GET.get('id')
    if not payment_id:
        return JsonResponse({'error': 'Missing payment id'}, status=400)

    sdk = SDK(settings.MERCADOPAGO_ACCESS_TOKEN)
    try:
        payment = sdk.payment().get(payment_id)['response']
    except Exception:
        logger.exception("MercadoPago payment lookup failed for payment_id %s", payment_id)
        return JsonResponse({'error': 'Could not fetch payment'}, status=400)

    order_number = payment.get('external_reference')
    if not order_number:
        return JsonResponse({'error': 'Missing external_reference'}, status=400)

    try:
        order = Order.objects.get(order_number=order_number)
    except Order.DoesNotExist:
        return JsonResponse({'error': 'Order not found'}, status=404)

    if order.status != OrderStatus.PAID and payment.get('status') == 'approved':
        finalize_paid_order(order, 'mercadopago', str(payment_id), order.total, payment)

    return JsonResponse({'received': True})
