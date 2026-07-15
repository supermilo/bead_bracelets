import json
import logging

import stripe
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from checkout.models import Order, OrderStatus
from payment.services import finalize_paid_order

logger = logging.getLogger(__name__)


def stripe_checkout(request, order_number):
    order = get_object_or_404(Order, order_number=order_number, status=OrderStatus.PENDING)
    return render(request, 'payment/stripe_checkout.html', {
        'order': order,
        'STRIPE_PUBLIC_KEY': settings.STRIPE_PUBLIC_KEY,
    })


def stripe_return(request, order_number):
    """Landing page for Stripe's return_url — only reached for payment
    methods/flows that need a full-page redirect (e.g. some 3DS variants),
    not the normal in-page confirmCardPayment path. Reads Stripe's
    redirect_status query param client-side and either finalizes the order
    (via the same confirm_payment_stripe endpoint the inline flow uses) or
    forwards to payment_failed — it must not assume failure outright, since
    a redirect-based confirmation can still succeed."""
    order = get_object_or_404(Order, order_number=order_number)
    return render(request, 'payment/stripe_return.html', {'order': order})


@require_POST
def create_payment_intent(request, order_number):
    order = get_object_or_404(Order, order_number=order_number, status=OrderStatus.PENDING)
    stripe.api_key = settings.STRIPE_SECRET_KEY

    try:
        intent = stripe.PaymentIntent.create(
            amount=int(order.total * 100),
            currency=order.currency.lower(),
            automatic_payment_methods={'enabled': True},
            metadata={'order_number': order.order_number},
        )
    except stripe.error.StripeError as err:
        logger.exception("Stripe PaymentIntent creation failed for order %s", order_number)
        return JsonResponse({'error': str(err)}, status=400)

    return JsonResponse({'client_secret': intent.client_secret})


@require_POST
def confirm_payment_stripe(request, order_number):
    order = get_object_or_404(Order, order_number=order_number, status=OrderStatus.PENDING)
    stripe.api_key = settings.STRIPE_SECRET_KEY

    try:
        data = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    payment_intent_id = data.get('payment_intent_id')
    if not payment_intent_id:
        return JsonResponse({'error': 'Missing payment_intent_id'}, status=400)

    try:
        intent = stripe.PaymentIntent.retrieve(payment_intent_id)
    except stripe.error.StripeError as err:
        logger.exception("Stripe PaymentIntent retrieval failed for order %s", order_number)
        return JsonResponse({'error': str(err)}, status=400)

    if intent.status != 'succeeded':
        return JsonResponse({'error': f'Payment not successful (status: {intent.status})'}, status=400)

    finalize_paid_order(order, 'stripe', intent.id, order.total, intent.to_dict())

    redirect_url = reverse('checkout:order_confirmation', args=[order.order_number])
    return JsonResponse({'redirect_url': redirect_url})
