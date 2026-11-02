from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.utils.html import format_html, format_html_join
from config.admin_site import WorkspaceAdminMixin

from .models import FAQ, SupportTicket
from .services import reply_ticket, set_status


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


@admin.register(FAQ)
class FAQAdmin(WorkspaceAdminMixin, admin.ModelAdmin):
    list_display = ["question", "topic", "is_published", "sort_order"]
    list_filter = ["topic", "is_published"]
    list_editable = ["is_published", "sort_order"]
    search_fields = ["question", "answer"]
