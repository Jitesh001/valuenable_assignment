from django.contrib import admin

from .models import PolicyQuote, PolicyType, PolicyVersion, Rider


@admin.register(PolicyType)
class PolicyTypeAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active")
    search_fields = ("code", "name")


@admin.register(Rider)
class RiderAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active")


@admin.register(PolicyVersion)
class PolicyVersionAdmin(admin.ModelAdmin):
    list_display = ("policy_type", "version", "effective_from", "effective_to")


@admin.register(PolicyQuote)
class PolicyQuoteAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "policy_type", "premium", "policy_term", "created_at")
    list_filter = ("policy_type", "premium_frequency")
    readonly_fields = ("result", "created_at")
