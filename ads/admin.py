from django import forms
from django.contrib import admin, messages
from django.forms.models import BaseInlineFormSet
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.core.exceptions import ValidationError
from django.utils.html import format_html
from config.admin_site import WorkspaceAdminMixin
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
        return super().get_queryset(request).prefetch_related("images")

    @admin.action(description="Убрать в архив", permissions=["change"])
    def archive_listings(self, request, queryset):
        for ad in queryset:
            ad.status = Ad.Status.ARCHIVED
            ad.save(update_fields=["status", "updated_at"])
            self.log_change(request, ad, "Объявление убрано в архив")
        self.message_user(request, "Объявления убраны в архив.", messages.SUCCESS)

    @admin.action(description="Опубликовать", permissions=["change"])
    def publish_listings(self, request, queryset):
        for ad in queryset:
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


User = get_user_model()
admin.site.unregister(User)


@admin.register(User)
class CampusUserAdmin(WorkspaceAdminMixin, UserAdmin):
    inlines = [ProfileInline]
    list_display = ["username", "email", "first_name", "last_name", "is_active", "is_staff"]
    list_filter = ["is_active", "is_staff", "groups", "date_joined"]


admin.site.register(Favorite)
# Seller/buyer message bodies are not part of the administrative workspace.
admin.site.site_header = "ДоскаСВФУ — управление"
admin.site.site_title = "ДоскаСВФУ"
