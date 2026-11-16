from django.contrib import admin
from config.admin_site import WorkspaceAdminMixin
from .models import CampusMessage, CampusPlace, Dormitory, Meeting, StudyRequest


@admin.register(Dormitory)
class DormitoryAdmin(WorkspaceAdminMixin, admin.ModelAdmin):
    list_display = ("name", "address", "is_active")
    search_fields = ("name", "address")


@admin.register(CampusPlace)
class PlaceAdmin(WorkspaceAdminMixin, admin.ModelAdmin):
    list_display = ["name", "meeting_hint", "is_active"]
    list_editable = ["meeting_hint", "is_active"]
    search_fields = ["name"]


@admin.register(StudyRequest)
class RequestAdmin(WorkspaceAdminMixin, admin.ModelAdmin):
    list_display = ["title", "author", "subject", "course", "is_active"]
    list_filter = ["is_active", "mode", "course"]
    search_fields = ["title", "subject", "place_note", "author__username"]
    readonly_fields = ["author", "created_at", "updated_at"]

    def has_add_permission(self, request):
        return False


@admin.register(Meeting)
class MeetingAdmin(WorkspaceAdminMixin, admin.ModelAdmin):
    list_display = ["id", "ad", "meeting_place_label", "starts_at", "status", "return_on"]
    list_select_related = ["ad", "place"]
    list_filter = ["status", "is_loan"]
    # Operators see operational state; participant identities and chat bodies stay private.
    fields = [
        "ad",
        "place",
        "place_note",
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


@admin.register(CampusMessage)
class CampusMessageAdmin(WorkspaceAdminMixin, admin.ModelAdmin):
    list_display = ["__str__", "author", "kind", "created_at"]
    list_filter = ["kind", "created_at"]
    search_fields = ["body", "author__username"]
    list_select_related = ["author"]
    ordering = ["-pk"]
    fields = ["author", "body", "kind", "request_status", "dormitory", "reply_to", "created_at"]
    readonly_fields = fields

    @admin.display(description="Статус запроса")
    def request_status(self, obj):
        if obj.kind == CampusMessage.Kind.WANTED:
            return obj.get_wanted_status_display()

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
