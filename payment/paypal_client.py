"""Thin wrapper around PayPal's Orders v2 REST API using plain `requests`
calls (OAuth2 client-credentials), rather than the paypalrestsdk package."""

import base64

import requests
from django.conf import settings

TOKEN_ENDPOINT = '/v1/oauth2/token'
ORDERS_ENDPOINT = '/v2/checkout/orders'
VERIFY_WEBHOOK_SIGNATURE_ENDPOINT = '/v1/notifications/verify-webhook-signature'


def generate_access_token():
    if not settings.PAYPAL_CLIENT_ID or not settings.PAYPAL_CLIENT_SECRET:
        raise ValueError('Missing PayPal credentials.')

    auth = base64.b64encode(
        f'{settings.PAYPAL_CLIENT_ID}:{settings.PAYPAL_CLIENT_SECRET}'.encode()
    ).decode()
    response = requests.post(
        f'{settings.PAYPAL_API_BASE_URL}{TOKEN_ENDPOINT}',
        data={'grant_type': 'client_credentials'},
        headers={'Authorization': f'Basic {auth}'},
    )
    response.raise_for_status()
    return response.json()['access_token']


def create_order(amount, currency, custom_id=None):
    access_token = generate_access_token()
    purchase_unit = {
        'amount': {
            'currency_code': currency,
            'value': f'{amount:.2f}',
        },
    }
    if custom_id:
        purchase_unit['custom_id'] = custom_id

    payload = {
        'intent': 'CAPTURE',
        'purchase_units': [purchase_unit],
    }
    response = requests.post(
        f'{settings.PAYPAL_API_BASE_URL}{ORDERS_ENDPOINT}',
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {access_token}',
        },
        json=payload,
    )
    response.raise_for_status()
    return response.json()


def capture_order(paypal_order_id):
    access_token = generate_access_token()
    response = requests.post(
        f'{settings.PAYPAL_API_BASE_URL}{ORDERS_ENDPOINT}/{paypal_order_id}/capture',
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {access_token}',
        },
    )
    response.raise_for_status()
    return response.json()


def verify_webhook_signature(transmission_headers, webhook_event, webhook_id):
    """Calls PayPal's verify-webhook-signature API to authenticate an
    incoming webhook payload. `transmission_headers` is a dict with keys
    transmission_id/transmission_time/cert_url/auth_algo/transmission_sig,
    pulled from the PAYPAL-TRANSMISSION-* request headers. Returns True only
    if PayPal reports verification_status == 'SUCCESS'."""
    access_token = generate_access_token()
    payload = {
        'transmission_id': transmission_headers['transmission_id'],
        'transmission_time': transmission_headers['transmission_time'],
        'cert_url': transmission_headers['cert_url'],
        'auth_algo': transmission_headers['auth_algo'],
        'transmission_sig': transmission_headers['transmission_sig'],
        'webhook_id': webhook_id,
        'webhook_event': webhook_event,
    }
    response = requests.post(
        f'{settings.PAYPAL_API_BASE_URL}{VERIFY_WEBHOOK_SIGNATURE_ENDPOINT}',
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {access_token}',
        },
        json=payload,
    )
    response.raise_for_status()
    return response.json().get('verification_status') == 'SUCCESS'
