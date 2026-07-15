from django.shortcuts import get_object_or_404, render

from .models import Order


def order_confirmation(request, order_number):
    order = get_object_or_404(
        Order.objects.prefetch_related('items__bracelet_configuration__items__item'),
        order_number=order_number,
    )
    return render(request, 'checkout/order_confirmation.html', {'order': order})
