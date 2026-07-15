from django.urls import path

from . import views

app_name = 'checkout'

urlpatterns = [
    path('<str:order_number>/confirmation/', views.order_confirmation, name='order_confirmation'),
]
