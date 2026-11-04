from django.urls import path

from . import views

urlpatterns = [
    path("checkout/", views.checkout, name="billing-checkout"),
    path("status/", views.billing_status, name="billing-status"),
    path("webhook/", views.webhook, name="billing-webhook"),
]
