import logging
import smtplib

import requests
import weasyprint
from celery import shared_task
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger(__name__)

CURRENCY_API_URL = 'https://open.er-api.com/v6/latest/USD'

# Matches this project's Stripe/PayPal/MercadoPago currency needs — MXN
# specifically for MercadoPago's settlement currency.
TARGET_CURRENCIES = {
    'USD': '$',
    'MXN': '$',
    'EUR': '€',
}


@shared_task(
    bind=True, max_retries=5, default_retry_delay=60,
    name='bracelet_builder.send_order_confirmation_email',
)
def send_order_confirmation_email(self, order_id):
    """Send one email per Order (bead list + total) with a PDF receipt
    attached, plus a matching admin sale notification."""
    from checkout.models import Order

    try:
        order = Order.objects.prefetch_related('items__bracelet_configuration__items__item').get(pk=order_id)
    except ObjectDoesNotExist as err:
        logger.error("Order not found for confirmation email: %s", err)
        raise err

    try:
        html = render_to_string('checkout/pdf/order_pdf.html', {'order': order, 'payment_method': order.gateway})
        pdf_bytes = weasyprint.HTML(string=html).write_pdf()
        pdf_name = f'order-{order.order_number}.pdf'

        sender = settings.DEFAULT_FROM_EMAIL
        raw_admins = settings.ADMINS
        if isinstance(raw_admins, str):
            admin_recipients = [raw_admins]
        elif raw_admins and isinstance(raw_admins[0], (list, tuple)):
            admin_recipients = [email for _name, email in raw_admins]
        else:
            admin_recipients = list(raw_admins)

        subject = f'Order Confirmation #{order.order_number}'
        body = 'Thank you for your purchase. Your receipt is attached.'
        customer_email = EmailMessage(subject, body, from_email=sender, to=[order.customer_email])
        customer_email.attach(pdf_name, pdf_bytes, 'application/pdf')
        customer_email.send()
        logger.info("Order confirmation email sent to %s for order %s", order.customer_email, order_id)

        if admin_recipients:
            admin_subject = f'New sale — Order #{order.order_number}'
            admin_body = (
                f'Order #{order.order_number} paid.\n'
                f'Customer: {order.customer_name} ({order.customer_email})\n'
                f'Phone: {order.customer_phone or "Not provided"}\n'
                f'Total: ${order.total} {order.currency}'
            )
            admin_email = EmailMessage(admin_subject, admin_body, from_email=sender, to=admin_recipients)
            admin_email.attach(pdf_name, pdf_bytes, 'application/pdf')
            admin_email.send()
            logger.info("Admin order notification sent for order %s", order_id)

    except smtplib.SMTPException as e:
        logger.error("SMTP error for order %s: %s", order_id, e)
        countdown = 2 ** self.request.retries
        raise self.retry(exc=e, countdown=countdown)
    except Exception:
        logger.exception("Error sending confirmation email for order #%s", order_id)
        raise

    return 0


@shared_task(name='bracelet_builder.update_currency_rates')
def update_currency_rates():
    """Fetch today's USD-relative exchange rates and log one
    CurrencyExchangeRate row per currency in TARGET_CURRENCIES, skipping any
    currency that already has a row for today — see CurrencyExchangeRate's
    docstring for why rows are appended rather than updated in place."""
    from payment.models import CurrencyExchangeRate

    try:
        response = requests.get(CURRENCY_API_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException:
        logger.exception("Failed to fetch currency rates from %s", CURRENCY_API_URL)
        raise

    rates = data.get('rates')
    if not rates:
        logger.warning("No 'rates' found in currency API response.")
        return 0

    today = timezone.localdate()
    for currency_code, symbol in TARGET_CURRENCIES.items():
        rate = rates.get(currency_code)
        if rate is None:
            logger.warning("Currency %s missing from API response.", currency_code)
            continue

        _, created = CurrencyExchangeRate.objects.get_or_create(
            currency_code=currency_code,
            created_at=today,
            defaults={'symbol': symbol, 'rate': rate},
        )
        if created:
            logger.info("New exchange rate for %s created: %s", currency_code, rate)
        else:
            logger.info("Exchange rate for %s already exists for today.", currency_code)

    return 0
