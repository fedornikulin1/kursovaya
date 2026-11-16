from urllib.parse import urlencode

from django import forms
from django.contrib import admin, messages
from django.forms.models import BaseInlineFormSet
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils.html import format_html
from django.views.decorators.cache import never_cache

from config.admin_site import WorkspaceAdminMixin
from .authentication import APPROVED_STUDENTS, block_account, revoke_refresh_tokens
from .models import Ad, AdImage, Category, Favorite, Message, Response, Review, UserProfile
from .validators import MAX_IMAGES


@admin.register(Category)
class CategoryAdmin(WorkspaceAdminMixin, admin.ModelAdmin):
    list_display = ["name", "sort_order", "is_active"]
    list_editable = ["sort_order", "is_active"]


class AdImageFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        total = sum(
            bool(form.cleaned_data.get("image"))
            for form in self.forms
            if not form.cleaned_data.get("DELETE", False)
        )
        if total + bool(self.instance.image) > MAX_IMAGES:
            raise forms.ValidationError("Всего можно сохранить до 8 фотографий, включая обложку.")


class AdImageInline(admin.TabularInline):
    model = AdImage
    formset = AdImageFormSet
    verbose_name = "Фотография"
    verbose_name_plural = "Дополнительные фотографии"
    extra = 0
    max_num = MAX_IMAGES

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "position":
            kwargs["label"] = "Порядок"
        return super().formfield_for_dbfield(db_field, request, **kwargs)


@admin.register(Ad)
class AdAdmin(WorkspaceAdminMixin, admin.ModelAdmin):
    list_display_links = ["title"]
    list_display = ["thumbnail", "title", "category", "author", "price", "status", "created_at"]
    list_filter = ["category", "status", "kind"]
    search_fields = ["title", "description", "author__username"]
    inlines = [AdImageInline]
    list_select_related = ["category", "author"]
    autocomplete_fields = ["author"]
    readonly_fields = ["created_at", "updated_at"]
    actions = ["archive_listings", "publish_listings"]

    @admin.display(description="Фото")
    def thumbnail(self, obj):
        if obj.cover:
            return format_html('<img class="admin-listing-thumb" src="{}" alt="">', obj.cover.url)
        return "—"

    def get_queryset(self, request):
        queryset = super().get_queryset(request).prefetch_related("images")
        if request.method == "POST" and request.resolver_match.url_name == "ads_ad_change":
            return queryset.select_for_update()
        return queryset

    @admin.action(description="Убрать в архив", permissions=["change"])
    def archive_listings(self, request, queryset):
        for ad in queryset:
            ad.status = Ad.Status.ARCHIVED
            ad.save(update_fields=["status", "updated_at"])
            self.log_change(request, ad, "Объявление убрано в архив")
        self.message_user(request, "Объявления убраны в архив.", messages.SUCCESS)

    @admin.action(description="Опубликовать", permissions=["change"])
    @transaction.atomic
    def publish_listings(self, request, queryset):
        for ad in queryset.select_for_update():
            ad.status = Ad.Status.ACTIVE
            try:
                ad.full_clean()
            except ValidationError:
                self.message_user(
                    request,
                    f"Не удалось опубликовать «{ad.title}»: проверьте поля объявления.",
                    messages.ERROR,
                )
                continue
            ad.save(update_fields=["status", "updated_at"])
            self.log_change(request, ad, "Объявление опубликовано")
        self.message_user(request, "Публикация проверенных объявлений завершена.")


@admin.register(Response)
class ResponseAdmin(admin.ModelAdmin):
    list_display = ["ad", "user", "is_accepted", "updated_at"]
    list_filter = ["is_accepted"]
    fields = ["ad", "user", "is_accepted", "created_at", "updated_at"]
    readonly_fields = fields

    def get_queryset(self, request):
        return super().get_queryset(request).filter(ad__isnull=False)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Review)
class ReviewAdmin(WorkspaceAdminMixin, admin.ModelAdmin):
    list_display = ["from_user", "to_user", "rating", "created_at"]
    list_filter = ["rating"]


class ProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    extra = 0
    readonly_fields = ["avatar", "cover"]


User = get_user_model()
admin.site.unregister(User)


@admin.register(User)
class CampusUserAdmin(WorkspaceAdminMixin, UserAdmin):
    inlines = [ProfileInline]
    list_display = ["username", "email", "first_name", "last_name", "is_active", "is_staff"]
    list_filter = ["is_active", "is_staff", "groups", "date_joined"]
    change_form_template = "admin/student_change_form.html"
    actions = ["approve_students", "block_accounts", "unblock_accounts"]

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser and (obj is None or not obj.is_superuser)

    def get_actions(self, request):
        actions = super().get_actions(request)
        # Use Django's individual deletion confirmation on the user's page.
        actions.pop("delete_selected", None)
        return actions

    def get_readonly_fields(self, request, obj=None):
        # Blocking must use the action so outstanding credentials are revoked.
        return ("is_active",) if obj is not None else ()

    def get_deleted_objects(self, objs, request):
        deleted, counts, permissions, protected = super().get_deleted_objects(objs, request)
        if request.user.is_superuser:
            # Read-only models such as conversations disallow standalone deletion.
            # Account deletion still uses the actual database cascade and protection rules.
            permissions = set()
        return deleted, counts, permissions, protected

    @transaction.atomic
    def delete_model(self, request, obj):
        revoke_refresh_tokens(obj)
        super().delete_model(request, obj)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        query = urlencode({"author__id__exact": object_id})
        context = {
            "listing_history_url": f"{reverse('admin:ads_ad_changelist')}?{query}"
            if request.user.has_perm("ads.view_ad") or request.user.has_perm("ads.change_ad") else "",
            "campus_history_url": f"{reverse('admin:campus_campusmessage_changelist')}?{query}"
            if request.user.has_perm("campus.view_campusmessage") or request.user.has_perm("campus.change_campusmessage") else "",
            "private_history_url": reverse("admin:student_dialogues", args=[int(object_id)])
            if request.user.is_superuser and object_id.isascii() and object_id.isdecimal()
            and len(object_id) <= 19 else "",
        }
        return super().change_view(request, object_id, form_url, {**context, **(extra_context or {})})

    def get_urls(self):
        return [
            path(
                "<int:object_id>/dialogues/",
                self.admin_site.admin_view(never_cache(self.private_dialogues)),
                name="student_dialogues",
            )
        ] + super().get_urls()

    def private_dialogues(self, request, object_id):
        if not request.user.is_superuser:
            raise PermissionDenied
        account = get_object_or_404(User, pk=object_id)
        threads = Response.objects.filter(
            Q(user=account) | Q(direct_peer=account) | Q(ad__author=account)
        ).select_related("ad", "user", "direct_peer").order_by("-updated_at", "-pk")

        class AuditForm(forms.Form):
            thread = forms.ModelChoiceField(queryset=threads, label="Диалог")
            reason = forms.CharField(min_length=8, max_length=200, label="Причина просмотра")
            page = forms.IntegerField(min_value=1, required=False, widget=forms.HiddenInput)

        form = AuditForm(request.POST if request.method == "POST" else None)
        page = None
        if request.method == "POST" and form.is_valid():
            thread = form.cleaned_data["thread"]
            reason = form.cleaned_data["reason"]
            self.log_change(request, account, f"Просмотр личного диалога № {thread.pk}. Причина: {reason}")
            page = Paginator(
                thread.messages.select_related("sender").order_by("pk"), 50
            ).get_page(form.cleaned_data["page"] or 1)
        return render(request, "admin/student_dialogues.html", {
            **self.admin_site.each_context(request),
            "title": f"Личные диалоги · {account.get_username()}",
            "account": account,
            "form": form,
            "page": page,
        })

    @admin.action(description="Подтвердить статус студента", permissions=["change"])
    def approve_students(self, request, queryset):
        from django.contrib.auth.models import Group

        group, _ = Group.objects.get_or_create(name=APPROVED_STUDENTS)
        for account in queryset.filter(is_staff=False, is_superuser=False):
            account.groups.add(group)
            self.log_change(request, account, "Подтверждён статус студента")
        self.message_user(request, "Выбранные студенческие аккаунты подтверждены.")

    @admin.action(description="Заблокировать аккаунты", permissions=["change"])
    @transaction.atomic
    def block_accounts(self, request, queryset):
        for account_id in queryset.filter(is_superuser=False).exclude(pk=request.user.pk).values_list("pk", flat=True):
            try:
                account, changed = block_account(account_id, actor=request.user)
            except ValidationError:
                continue
            if changed:
                self.log_change(request, account, "Вход заблокирован, токены обновления отозваны")
        self.message_user(request, "Выбранные аккаунты заблокированы.")

    @admin.action(description="Снять блокировку аккаунтов", permissions=["change"])
    def unblock_accounts(self, request, queryset):
        for account in queryset.filter(is_superuser=False, is_active=False):
            account.is_active = True
            account.save(update_fields=["is_active"])
            self.log_change(request, account, "Блокировка снята")
        self.message_user(request, "Блокировка выбранных аккаунтов снята.")


admin.site.register(Favorite)
# Seller/buyer message bodies are not part of the administrative workspace.
admin.site.site_header = "ДоскаСВФУ — управление"
admin.site.site_title = "ДоскаСВФУ"
