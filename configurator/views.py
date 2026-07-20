from collections import Counter
from decimal import Decimal

from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from checkout.models import Order, OrderItem

from .models import (
    BraceletBase,
    BraceletConfiguration,
    BraceletConfigurationItem,
    BraceletItem,
    ItemCategory,
    LeatherBraceletBase,
)

CORD_ELASTIC = 'elastic'
CORD_LEATHER = 'leather'
CORD_TYPES = {CORD_ELASTIC, CORD_LEATHER}


def _get_session_data(request):
    session_data = request.session.get('bracelet_build')
    if session_data is None:
        session_data = {'cord_type': None, 'base_id': None, 'items': []}
        request.session['bracelet_build'] = session_data
    return session_data


def _active_cord_type(session_data):
    """Sessions created before cord-type selection existed have no
    'cord_type' key at all - they only ever built elastic bracelets, so
    treat a missing key the same as an explicit 'elastic' pick."""
    return session_data.get('cord_type') or CORD_ELASTIC


def _display_cord_type(session_data):
    """Distinguishes 'nothing chosen yet' (None - the size selector should
    show only the cord-type step) from 'a type is active' (elastic or
    leather - the size selector should show that type's sizes too). Unlike
    _active_cord_type, this can return None: a brand-new session has neither
    an explicit cord_type nor a resolved base, and should render as step 1
    only. A legacy session with a base_id but no cord_type key has already
    resolved to elastic via _active_cord_type, so it's shown as such rather
    than bounced back to step 1."""
    cord_type = session_data.get('cord_type')
    if cord_type in CORD_TYPES:
        return cord_type
    if session_data.get('base_id') is not None:
        return CORD_ELASTIC
    return None


def _get_active_base(session_data):
    base_id = session_data.get('base_id')
    if base_id is None:
        return None
    model = LeatherBraceletBase if _active_cord_type(session_data) == CORD_LEATHER else BraceletBase
    return model.objects.filter(pk=base_id).first()


def _tray_context(session_data, error=None):
    is_leather = _active_cord_type(session_data) == CORD_LEATHER
    base = _get_active_base(session_data)
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

    total_slots = 0
    if base is not None:
        total_slots = base.slot_count if is_leather else base.total_slots

    return {
        'base': None if is_leather else base,
        'leather_base': base if is_leather else None,
        'cord_type': _display_cord_type(session_data),
        'tray_items': tray_items,
        'used_slots': used_slots,
        'total_slots': total_slots,
        'total_price': total_price,
        'error': error,
    }


@ensure_csrf_cookie
def index(request):
    categories = ItemCategory.objects.all()
    bases = BraceletBase.objects.order_by('total_slots')
    leather_bases = LeatherBraceletBase.objects.order_by('size', 'name')
    session_data = _get_session_data(request)
    context = {'categories': categories, 'bases': bases, 'leather_bases': leather_bases}
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

    is_leather = _active_cord_type(session_data) == CORD_LEATHER
    base_model = LeatherBraceletBase if is_leather else BraceletBase
    base = get_object_or_404(base_model, pk=session_data['base_id'])
    base_total_slots = base.slot_count if is_leather else base.total_slots

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
            if used_slots + item.slot_width > base_total_slots:
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
def clear_bracelet(request):
    """Empty the tray's item list, keeping the chosen base/size intact —
    clearing beads and switching size are different intents, and forcing a
    re-pick of size after a clear would just be an extra step for no reason."""
    session_data = _get_session_data(request)
    session_data['items'] = []
    request.session['bracelet_build'] = session_data
    request.session.modified = True

    return render(
        request, 'configurator/partials/build_tray.html', _tray_context(session_data)
    )


def _render_size_selector_and_tray(request, session_data, error):
    """Shared by select_cord_type and select_bracelet_base - both re-render
    the size selector (primary target) plus the build tray (out-of-band
    swap), the same two-widget response pattern select_bracelet_base always
    used, now type-aware on top."""
    bases = BraceletBase.objects.order_by('total_slots')
    leather_bases = LeatherBraceletBase.objects.order_by('size', 'name')
    tray_context = _tray_context(session_data)
    selector_html = render_to_string(
        'configurator/partials/size_selector.html',
        {
            'bases': bases,
            'leather_bases': leather_bases,
            'cord_type': tray_context['cord_type'],
            'base': tray_context['base'],
            'leather_base': tray_context['leather_base'],
            'error': error,
        },
        request=request,
    )
    tray_context['oob'] = True
    tray_html = render_to_string(
        'configurator/partials/build_tray.html', tray_context, request=request
    )
    return HttpResponse(selector_html + tray_html)


@require_POST
def select_cord_type(request):
    """First step of the build flow: pick elastic vs. leather before a size
    can be chosen. Switching cord type invalidates any previously chosen
    base_id (a leather pk is meaningless as a BraceletBase pk and vice
    versa), so it's reset here - the subsequent select_bracelet_base call
    re-validates tray capacity against whichever specific size gets picked
    next, same as an ordinary size switch does today."""
    session_data = _get_session_data(request)

    cord_type = request.POST.get('cord_type')
    error = None
    if cord_type not in CORD_TYPES:
        error = 'That bracelet type could not be found.'
    else:
        session_data['cord_type'] = cord_type
        session_data['base_id'] = None
        request.session['bracelet_build'] = session_data
        request.session.modified = True

    return _render_size_selector_and_tray(request, session_data, error)


@require_POST
def select_bracelet_base(request):
    session_data = _get_session_data(request)
    is_leather = _active_cord_type(session_data) == CORD_LEATHER
    base_model = LeatherBraceletBase if is_leather else BraceletBase

    new_base = None
    try:
        new_base = base_model.objects.filter(pk=int(request.POST.get('base_id'))).first()
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
            new_total_slots = new_base.slot_count if is_leather else new_base.total_slots
            if used_slots > new_total_slots:
                error = 'Switching to this size would exceed its capacity — remove some items first.'

    if error is None:
        session_data['base_id'] = new_base.id
        request.session['bracelet_build'] = session_data
        request.session.modified = True

    return _render_size_selector_and_tray(request, session_data, error)


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
    is_leather = _active_cord_type(session_data) == CORD_LEATHER
    base_model = LeatherBraceletBase if is_leather else BraceletBase
    base = get_object_or_404(base_model, pk=session_data.get('base_id'))

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
            base=None if is_leather else base,
            leather_base=base if is_leather else None,
            session_key=request.session.session_key,
            is_finalized=True,
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
