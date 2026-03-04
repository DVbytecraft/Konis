from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "action", "object_type", "object_id", "created_at")
    list_filter = ("action", "object_type")
    search_fields = ("user__username", "action")
    readonly_fields = ("user", "action", "object_type", "object_id", "extra", "created_at")
    date_hierarchy = "created_at"
