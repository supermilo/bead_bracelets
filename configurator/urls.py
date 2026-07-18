from django.urls import path

from . import views

app_name = 'configurator'

urlpatterns = [
    path('', views.index, name='index'),
    path('items/carousel/', views.bracelet_item_carousel, name='bracelet_item_carousel'),
    path('bracelet/add/', views.add_bracelet_item, name='add_bracelet_item'),
    path('bracelet/remove/', views.remove_bracelet_item, name='remove_bracelet_item'),
    path('bracelet/clear/', views.clear_bracelet, name='clear_bracelet'),
    path('bracelet/select-cord-type/', views.select_cord_type, name='select_cord_type'),
    path('bracelet/select-base/', views.select_bracelet_base, name='select_bracelet_base'),
    path('checkout/', views.checkout, name='checkout'),
    path('bracelet/finalize/', views.finalize_bracelet, name='finalize_bracelet'),
]
