from django.contrib import admin

from .models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("email", "is_active", "is_staff", "created_at")
    search_fields = ("email",)
    readonly_fields = ("created_at", "updated_at", "last_login", "date_joined")
    # Intentionally NOT exposing decrypted PII in list view; raw encrypted blobs stay hidden.
    fields = ("email", "is_active", "is_staff", "is_superuser", "last_login", "date_joined")
