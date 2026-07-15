from collections import Counter
from decimal import Decimal

from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from checkout.models import Order, OrderItem

from .models import BraceletBase, BraceletConfiguration, BraceletConfigurationItem, BraceletItem, ItemCategory


def _get_session_data(request):
    session_data = request.session.get('bracelet_build')
    if session_data is None:
        session_data = {'base_id': None, 'items': []}
        request.session['bracelet_build'] = session_data
    return session_data


def _tray_context(session_data, error=None):
    base = BraceletBase.objects.filter(pk=session_data.get('base_id')).first()
    item_ids = session_data.get('items', [])
    items_by_id = BraceletItem.objects.in_bulk(item_ids)

    tray_items = []
    used_slots = 0
    total_price = base.base_price if base else Decimal('0')
    for position, item_id in enumerate(item_ids):
        item = items_by_id.get(item_id)
        if item is None:
            continue
        tray_items.append({'position': position, 'item': item})
        used_slots += item.slot_width
        total_price += item.price

    return {
        'base': base,
        'tray_items': tray_items,
        'used_slots': used_slots,
        'total_slots': base.total_slots if base else 0,
        'total_price': total_price,
        'error': error,
    }


@ensure_csrf_cookie
def index(request):
    categories = ItemCategory.objects.all()
    bases = BraceletBase.objects.order_by('total_slots')
    session_data = _get_session_data(request)
    context = {'categories': categories, 'bases': bases}
    context.update(_tray_context(session_data))
    return render(request, 'configurator/bracelet_builder.html', context)


def bracelet_item_carousel(request):
    category_slug = request.GET.get('category')
    items = list(BraceletItem.objects.filter(
        is_active=True, category__slug=category_slug
    ).order_by('name'))
    session_data = _get_session_data(request)
    has_base = session_data.get('base_id') is not None

    existing_counts = Counter(session_data.get('items', []))
    for item in items:
        item.remaining_stock = item.stock - existing_counts.get(item.id, 0)

    return render(
        request, 'configurator/partials/item_carousel.html', {'items': items, 'has_base': has_base}
    )


@require_POST
def add_bracelet_item(request):
    session_data = _get_session_data(request)

    if session_data.get('base_id') is None:
        return render(
            request, 'configurator/partials/build_tray.html',
            _tray_context(session_data, error='Choose a bracelet size before adding beads.'),
        )

    base = get_object_or_404(BraceletBase, pk=session_data['base_id'])

    item = None
    try:
        item = BraceletItem.objects.filter(pk=int(request.POST.get('item_id'))).first()
    except (TypeError, ValueError):
        item = None

    error = None
    if item is None:
        error = 'That item could not be found.'
    elif not item.is_active or item.stock <= 0:
        error = f'{item.name} is currently out of stock.'
    else:
        existing_count = session_data['items'].count(item.id)
        if existing_count + 1 > item.stock:
            error = f'Only {item.stock} in stock — you already have {existing_count} in your bracelet.'
        else:
            slot_widths = BraceletItem.objects.in_bulk(session_data['items'])
            used_slots = sum(
                slot_widths[i].slot_width for i in session_data['items'] if i in slot_widths
            )
            if used_slots + item.slot_width > base.total_slots:
                error = 'Not enough room left on this bracelet.'

    if error is None:
        session_data['items'].append(item.id)
        request.session['bracelet_build'] = session_data
        request.session.modified = True

    return render(
        request, 'configurator/partials/build_tray.html', _tray_context(session_data, error=error)
    )


@require_POST
def remove_bracelet_item(request):
    session_data = _get_session_data(request)

    try:
        position = int(request.POST.get('position'))
        session_data['items'].pop(position)
    except (TypeError, ValueError, IndexError):
        pass
    else:
        request.session['bracelet_build'] = session_data
        request.session.modified = True

    return render(
        request, 'configurator/partials/build_tray.html', _tray_context(session_data)
    )


@require_POST
def select_bracelet_base(request):
    session_data = _get_session_data(request)

    new_base = None
    try:
        new_base = BraceletBase.objects.filter(pk=int(request.POST.get('base_id'))).first()
    except (TypeError, ValueError):
        new_base = None

    error = None
    if new_base is None:
        error = 'That bracelet size could not be found.'
    else:
        item_ids = session_data.get('items', [])
        if item_ids:
            slot_widths = BraceletItem.objects.in_bulk(item_ids)
            used_slots = sum(slot_widths[i].slot_width for i in item_ids if i in slot_widths)
            if used_slots > new_base.total_slots:
                error = 'Switching to this size would exceed its capacity — remove some items first.'

    if error is None:
        session_data['base_id'] = new_base.id
        request.session['bracelet_build'] = session_data
        request.session.modified = True

    bases = BraceletBase.objects.order_by('total_slots')
    tray_context = _tray_context(session_data)
    selector_html = render_to_string(
        'configurator/partials/size_selector.html',
        {'bases': bases, 'base': tray_context['base'], 'error': error},
        request=request,
    )
    tray_context['oob'] = True
    tray_html = render_to_string(
        'configurator/partials/build_tray.html', tray_context, request=request
    )
    return HttpResponse(selector_html + tray_html)


def checkout(request):
    session_data = _get_session_data(request)
    if not session_data.get('items'):
        return redirect('configurator:index')

    context = _tray_context(session_data)
    context.update(customer_name='', customer_email='', customer_phone='')
    return render(request, 'configurator/checkout.html', context)


@require_POST
def finalize_bracelet(request):
    session_data = _get_session_data(request)
    item_ids = session_data.get('items', [])
    base = get_object_or_404(BraceletBase, pk=session_data.get('base_id'))

    customer_name = request.POST.get('customer_name', '').strip()
    customer_email = request.POST.get('customer_email', '').strip()
    customer_phone = request.POST.get('customer_phone', '').strip()

    errors = []
    if not item_ids:
        errors.append('Your bracelet tray is empty.')
    if not customer_name:
        errors.append('Name is required.')
    if not customer_email:
        errors.append('Email is required.')

    # Fresh-from-DB stock re-validation. add_bracelet_item only checks
    # item.stock > 0 per individual add, never cumulative demand — so the
    # same 1-in-stock bead can be added 3 times without any add-time
    # rejection. This Counter-based check against the DB is the real
    # safety net, right before an Order gets created.
    counts = Counter(item_ids)
    items_by_id = BraceletItem.objects.in_bulk(counts.keys())
    for item_id, needed in counts.items():
        item = items_by_id.get(item_id)
        if item is None or not item.is_active:
            errors.append('An item in your tray is no longer available.')
        elif item.stock < needed:
            errors.append(f'Only {item.stock} of "{item.name}" left (you selected {needed}).')

    if errors:
        context = _tray_context(session_data, error=' '.join(errors))
        context.update(
            customer_name=customer_name, customer_email=customer_email, customer_phone=customer_phone,
        )
        return render(request, 'configurator/checkout.html', context, status=400)

    if not request.session.session_key:
        request.session.save()

    with transaction.atomic():
        configuration = BraceletConfiguration.objects.create(
            base=base, session_key=request.session.session_key, is_finalized=True,
        )
        BraceletConfigurationItem.objects.bulk_create([
            BraceletConfigurationItem(configuration=configuration, item_id=item_id, position=position)
            for position, item_id in enumerate(item_ids)
        ])

        total_price = base.base_price + sum(items_by_id[i].price for i in item_ids)

        order = Order.objects.create(
            session_key=request.session.session_key,
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            total=total_price,
        )
        OrderItem.objects.create(
            order=order,
            bracelet_configuration=configuration,
            item_title=f'{base.name} Bracelet',
            unit_price=total_price,
            quantity=1,
            total_price=total_price,
        )

    del request.session['bracelet_build']
    request.session.modified = True

    return redirect('payment:choose_gateway', order_number=order.order_number)
