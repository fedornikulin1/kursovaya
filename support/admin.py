from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.template.defaultfilters import linebreaksbr
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join
from django.views.decorators.http import require_http_methods

from ads.authentication import block_account
from ads.models import Ad
from campus.models import CampusMessage
from config.admin_site import WorkspaceAdminMixin

from .models import ContentReport, FAQ, SupportTicket
from .services import notify_report_decision, reply_ticket, set_status


class StaffReplyForm(forms.ModelForm):
    reply_text = forms.CharField(
        label="Ответ пользователю",
        required=False,
        max_length=4000,
        widget=forms.Textarea(
            attrs={
                "rows": 5,
                "placeholder": "Напишите ответ. Пользователь увидит его в разделе «Помощь».",
            }
        ),
    )
    close_after_reply = forms.BooleanField(label="Закрыть обращение после ответа", required=False)

    class Meta:
        model = SupportTicket
        fields = []

    def clean(self):
        data = super().clean()
        if self.instance.status == SupportTicket.Status.CLOSED and data.get("reply_text"):
            raise ValidationError(
                "Обращение закрыто. Сначала откройте его действием в списке обращений."
            )
        if data.get("close_after_reply") and not data.get("reply_text"):
            raise ValidationError(
                "Чтобы закрыть с ответом, заполните ответ. Без ответа закройте обращение действием в списке."
            )
        return data


@admin.register(SupportTicket)
class SupportTicketAdmin(WorkspaceAdminMixin, admin.ModelAdmin):
    form = StaffReplyForm
    view_on_site = False  # The public ticket page is accessible only to its author.
    list_display = ["number", "subject", "user", "topic", "status", "updated_at"]
    list_display_links = ["number", "subject"]
    list_filter = ["status", "topic", "created_at"]
    search_fields = ["subject", "user__username", "user__email"]
    list_select_related = ["user"]
    readonly_fields = [
        "user",
        "subject",
        "topic",
        "status",
        "created_at",
        "updated_at",
        "conversation_history",
    ]
    fieldsets = [
        (
            "Обращение",
            {"fields": ["subject", "user", "topic", "status", ("created_at", "updated_at")]},
        ),
        ("Переписка с пользователем", {"fields": ["conversation_history"]}),
        (
            "Ответ поддержки",
            {
                "fields": ["reply_text", "close_after_reply"],
                "description": "Ответ сохраняется в истории обращения. Для отправки нажмите «Сохранить».",
            },
        ),
    ]
    actions = ["close_tickets", "reopen_tickets"]

    def get_queryset(self, request):
        queryset = super().get_queryset(request).select_related("user")
        if request.method == "POST" and request.resolver_match.url_name.endswith("_change"):
            # Change forms are transactional: keep validation and reply together
            # if another operator or the user closes the ticket concurrently.
            queryset = queryset.select_for_update()
        return queryset

    @admin.display(description="Номер")
    def number(self, obj):
        return f"№ {obj.pk}"

    @admin.display(description="История")
    def conversation_history(self, obj):
        from django.utils import timezone

        return format_html(
            '<div class="support-admin-history">{}</div>',
            format_html_join(
                "",
                '<article class="support-admin-message {}"><header><strong>{}</strong><time>{}</time></header><p>{}</p></article>',
                (
                    (
                        "staff" if message.from_staff else "user",
                        (
                            "Поддержка"
                            if message.from_staff
                            else obj.user.get_full_name() or obj.user.username
                        ),
                        timezone.localtime(message.created_at).strftime("%d.%m.%Y %H:%M"),
                        message.text,
                    )
                    for message in obj.messages.select_related("sender")
                ),
            ),
        )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        text = form.cleaned_data.get("reply_text")
        if text:
            reply_ticket(
                ticket=obj,
                actor=request.user,
                text=text,
                staff=True,
                close=form.cleaned_data.get("close_after_reply", False),
            )
            obj.refresh_from_db()
        # Metadata and history are immutable here; only the service writes a reply.

    def change_status(self, request, queryset, closed):
        for ticket in queryset:
            set_status(ticket=ticket, actor=request.user, closed=closed, staff=True)
            self.log_change(request, ticket, "Закрыто" if closed else "Открыто повторно")
        self.message_user(request, "Статусы обращений обновлены.", messages.SUCCESS)

    @admin.action(description="Закрыть выбранные обращения", permissions=["change"])
    def close_tickets(self, request, queryset):
        self.change_status(request, queryset, True)

    @admin.action(description="Открыть повторно", permissions=["change"])
    def reopen_tickets(self, request, queryset):
        self.change_status(request, queryset, False)


class ContentReportDecisionForm(forms.ModelForm):
    class Meta:
        model = ContentReport
        fields = ["status", "moderator_note"]
        widgets = {"moderator_note": forms.Textarea(attrs={"rows": 5})}

    def clean(self):
        data = super().clean()
        if data.get("status") in {ContentReport.Status.RESOLVED, ContentReport.Status.DISMISSED}:
            if not data.get("moderator_note"):
                self.add_error("moderator_note", "Укажите, почему вы приняли это решение.")
        return data


class ModerationActionForm(forms.Form):
    reason = forms.CharField(label="Причина решения", max_length=2000, widget=forms.Textarea(attrs={"rows": 4}))


@admin.register(ContentReport)
class ContentReportAdmin(WorkspaceAdminMixin, admin.ModelAdmin):
    form = ContentReportDecisionForm
    change_form_template = "admin/content_report_change_form.html"
    moderation_labels = {
        "hide-listing": "Скрыть объявление",
        "remove-message": "Удалить сообщение",
        "block-author": "Заблокировать автора",
    }
    list_display = ["target_label", "kind", "reason", "status", "reporter", "created_at"]
    list_filter = ["status", "kind", "reason", "created_at"]
    list_select_related = ["reporter"]
    search_fields = ["target_label", "target_author", "reporter__username"]
    readonly_fields = [
        "reporter", "kind", "reason", "created_at", "updated_at", "target_link",
        "target_excerpt_text", "complaint_text", "ticket_link",
    ]
    fieldsets = [
        (
            "Жалоба",
            {"fields": ["kind", "target_link", "reporter", "reason", "complaint_text", "ticket_link", "created_at"]},
        ),
        ("Текст публикации на момент жалобы", {"fields": ["target_excerpt_text"]}),
        ("Решение", {"fields": ["status", "moderator_note", "updated_at"]}),
    ]

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.method == "POST" and request.resolver_match.url_name in {
            "support_contentreport_change", "support_contentreport_moderate",
        }:
            return queryset.select_for_update()
        return queryset

    def get_urls(self):
        return [
            path(
                "<int:object_id>/moderation/<str:action>/",
                self.admin_site.admin_view(require_http_methods(["GET", "HEAD", "POST"])(self.moderate)),
                name="support_contentreport_moderate",
            ),
        ] + super().get_urls()

    def can_moderate(self, request, report, action):
        if not self.has_change_permission(request, report):
            return False
        if action == "hide-listing":
            return report.kind == ContentReport.Kind.LISTING and request.user.has_perm("ads.change_ad")
        if action == "remove-message":
            return report.kind == ContentReport.Kind.CHAT and request.user.has_perm("campus.delete_campusmessage")
        return (
            action == "block-author" and request.user.is_superuser and report.target_account_id
            and not report.target_account.is_superuser and report.target_account_id != request.user.pk
        )

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        if obj and self.has_change_permission(request, obj):
            context["moderation_links"] = [
                (reverse("admin:support_contentreport_moderate", args=[obj.pk, action]), label)
                for action, label in self.moderation_labels.items()
                if self.can_moderate(request, obj, action)
            ]
        return super().render_change_form(request, context, add, change, form_url, obj)

    @transaction.atomic
    def moderate(self, request, object_id, action):
        if not self.has_change_permission(request):
            raise PermissionDenied
        report = get_object_or_404(self.get_queryset(request), pk=object_id)
        if not self.can_moderate(request, report, action):
            raise PermissionDenied
        form = ModerationActionForm(request.POST if request.method == "POST" else None)
        label = self.moderation_labels[action]
        if form.is_bound and form.is_valid():
            try:
                event = self.apply_moderation(request, report, action, form.cleaned_data["reason"])
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                self.message_user(request, event, messages.SUCCESS)
                return redirect("admin:support_contentreport_change", report.pk)
        return render(request, "admin/content_report_moderate.html", {
            **self.admin_site.each_context(request), "opts": self.model._meta,
            "title": label, "report": report, "form": form,
        })

    def apply_moderation(self, request, report, action, reason):
        if action == "hide-listing":
            target = Ad.objects.select_for_update().filter(pk=report.target_id).first()
            if not target or target.moderation_hidden:
                raise ValidationError("Объявление уже скрыто или удалено.")
            target.moderation_hidden = True
            target.status = Ad.Status.ARCHIVED
            target.save(update_fields=["moderation_hidden", "status", "updated_at"])
            event = "Объявление скрыто"
        elif action == "remove-message":
            target = CampusMessage.objects.select_for_update().filter(pk=report.target_id).first()
            if not target:
                raise ValidationError("Сообщение уже удалено.")
            self.admin_site.get_model_admin(CampusMessage).log_deletions(
                request, CampusMessage.objects.filter(pk=target.pk),
            )
            target.delete()
            event = "Сообщение удалено"
        else:
            target, changed = block_account(report.target_account_id, actor=request.user)
            if not changed:
                raise ValidationError("Аккаунт уже заблокирован.")
            event = "Автор заблокирован"

        audit = f"{event} по жалобе № {report.pk}. Причина: {reason}"
        if action != "remove-message":
            self.admin_site.get_model_admin(type(target)).log_change(request, target, audit)
        previous_status = report.status
        report.status = ContentReport.Status.RESOLVED
        report.moderator_note = reason
        report.save(update_fields=["status", "moderator_note", "updated_at"])
        notify_report_decision(report, previous_status=previous_status)
        self.log_change(request, report, audit)
        return event

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        notify_report_decision(obj, previous_status=form.initial.get("status"))

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Публикация")
    def target_link(self, obj):
        name = "admin:ads_ad_change" if obj.kind == ContentReport.Kind.LISTING else "admin:campus_campusmessage_change"
        return format_html(
            '<a href="{}">{} №{}</a> · @{} · <a href="{}">В админке</a>',
            obj.target_url, obj.target_label, obj.target_id, obj.target_author,
            reverse(name, args=[obj.target_id]),
        )

    @admin.display(description="Текст публикации")
    def target_excerpt_text(self, obj):
        return linebreaksbr(obj.target_excerpt)

    @admin.display(description="Объяснение заявителя")
    def complaint_text(self, obj):
        first = obj.ticket.messages.first()
        return linebreaksbr(first.text) if first else None

    @admin.display(description="Обращение в поддержку")
    def ticket_link(self, obj):
        return format_html(
            '<a href="{}">Обращение №{}</a>',
            reverse("admin:support_supportticket_change", args=[obj.ticket_id]), obj.ticket_id,
        )

    def construct_change_message(self, request, form, formsets, add=False):
        if form.has_changed():
            return f"{form.instance.get_status_display()} · {form.instance.moderator_note or 'Без комментария'}"
        return super().construct_change_message(request, form, formsets, add)


@admin.register(FAQ)
class FAQAdmin(WorkspaceAdminMixin, admin.ModelAdmin):
    list_display = ["question", "topic", "is_published", "sort_order"]
    list_filter = ["topic", "is_published"]
    list_editable = ["is_published", "sort_order"]
    search_fields = ["question", "answer"]
