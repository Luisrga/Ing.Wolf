from django.contrib import admin

from .models import Broker, RemovalRequest


@admin.register(Broker)
class BrokerAdmin(admin.ModelAdmin):
    list_display = ("name", "opt_out_url", "active")
    list_filter = ("active",)
    search_fields = ("name",)


@admin.register(RemovalRequest)
class RemovalRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "broker", "status", "attempts", "updated_at")
    list_filter = ("status", "broker")
    search_fields = ("user__username", "broker__name")
    readonly_fields = ("created_at", "updated_at", "submitted_at")
