from django.contrib import admin
from config.admin_site import WorkspaceAdminMixin
from .models import CampusPlace, Meeting, StudyRequest


@admin.register(CampusPlace)
class PlaceAdmin(WorkspaceAdminMixin, admin.ModelAdmin):
    list_display = ["name", "meeting_hint", "is_active"]
    list_editable = ["meeting_hint", "is_active"]
    search_fields = ["name"]


@admin.register(StudyRequest)
class RequestAdmin(WorkspaceAdminMixin, admin.ModelAdmin):
    list_display = ["title", "author", "subject", "course", "is_active"]
    list_filter = ["is_active", "mode", "course"]
    search_fields = ["title", "subject", "author__username"]
    readonly_fields = ["author", "created_at", "updated_at"]

    def has_add_permission(self, request):
        return False


@admin.register(Meeting)
class MeetingAdmin(WorkspaceAdminMixin, admin.ModelAdmin):
    list_display = ["id", "ad", "place", "starts_at", "status", "return_on"]
    list_filter = ["status", "is_loan"]
    # Operators see operational state; participant identities and chat bodies stay private.
    fields = [
        "ad",
        "place",
        "starts_at",
        "ends_at",
        "return_on",
        "status",
        "created_at",
        "updated_at",
    ]
    readonly_fields = fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
