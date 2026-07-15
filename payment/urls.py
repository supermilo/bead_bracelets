from django.urls import path

from . import views

app_name = 'payment'

urlpatterns = [
    path('<str:order_number>/', views.choose_gateway, name='choose_gateway'),
    path('<str:order_number>/process/', views.process_payment, name='process_payment'),
    path('<str:order_number>/failed/', views.payment_failed, name='payment_failed'),

    path('<str:order_number>/stripe/', views.stripe_checkout, name='stripe_checkout'),
    path('<str:order_number>/stripe/intent/', views.create_payment_intent, name='create_payment_intent'),
    path('<str:order_number>/stripe/confirm/', views.confirm_payment_stripe, name='confirm_payment_stripe'),
    path('<str:order_number>/stripe/return/', views.stripe_return, name='stripe_return'),

    path('<str:order_number>/paypal/', views.paypal_checkout, name='paypal_checkout'),
    path('<str:order_number>/paypal/create/', views.create_paypal_order, name='create_paypal_order'),
    path('<str:order_number>/paypal/capture/', views.capture_paypal_order, name='capture_paypal_order'),
    path('paypal/webhook/', views.paypal_webhook, name='paypal_webhook'),

    path('<str:order_number>/mercadopago/', views.mercadopago_checkout, name='mercadopago_checkout'),
    path('mercadopago/webhook/', views.mercadopago_webhook, name='mercadopago_webhook'),
]
