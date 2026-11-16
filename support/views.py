from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.encoding import uri_to_iri
from django.utils.text import Truncator
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST, require_safe

from ads.models import Ad
from ads.selectors import visible_ads
from campus.chat import chat_message_url
from campus.models import CampusMessage
from .forms import ProfileReportForm, ReplyForm, TicketForm
from .assistant import answer_question, assistant_enabled
from .models import ContentReport, FAQ, SupportTicket
from .selectors import tickets_for
from .services import create_ticket, mark_answers_read, reply_ticket, report_content, set_status


@require_safe
def help_center(request):
    return render(
        request,
        "support/help.html",
        {
            "faqs": FAQ.objects.filter(is_published=True),
            "topics": SupportTicket.Topic.choices,
            "assistant_enabled": assistant_enabled(),
        },
    )


class AssistantQuestionForm(forms.Form):
    question = forms.CharField(
        label="Вопрос о площадке", max_length=600, widget=forms.Textarea(attrs={"rows": 4})
    )


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def ask_assistant(request):
    if not assistant_enabled():
        raise Http404
    form = AssistantQuestionForm(request.POST if request.method == "POST" else None)
    answer = ""
    if form.is_bound and form.is_valid():
        answer = answer_question(form.cleaned_data["question"])
        if not answer:
            form.add_error(None, "Помощник сейчас не ответил. Вопрос можно отправить сотруднику.")
    return render(request, "support/assistant.html", {"form": form, "answer": answer})


@login_required
@require_safe
@never_cache
def ticket_list(request):
    return render(request, "support/tickets.html", {"tickets": tickets_for(request.user)})


@login_required
@require_http_methods(["GET", "POST"])
@never_cache
def ticket_create(request):
    form = TicketForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            ticket = create_ticket(user=request.user, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            return redirect(ticket)
    return render(request, "support/ticket_form.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
@never_cache
def report_profile(request, username):
    target = get_object_or_404(get_user_model(), username=username, is_active=True)
    if target.pk == request.user.pk:
        raise PermissionDenied

    form = ProfileReportForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        profile_url = uri_to_iri(reverse("ads:user_profile", args=[target.get_username()]))
        subject = Truncator(f"Жалоба на профиль @{target.get_username()}").chars(150)
        report = (
            f"Профиль: @{target.get_username()} (№ {target.pk})\n"
            f"Страница: {profile_url}\n"
            f"Причина: {form.reason_label}\n\n"
            f"{form.cleaned_data['text']}"
        )
        try:
            ticket = create_ticket(
                user=request.user, subject=subject, topic=SupportTicket.Topic.SAFETY, text=report
            )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Жалоба отправлена. Ответ появится в обращении.")
            return redirect(ticket)
    return render(request, "support/profile_report.html", {"form": form, "target": target})


@login_required
@require_http_methods(["GET", "HEAD", "POST"])
@never_cache
def report_listing(request, pk):
    ad = get_object_or_404(visible_ads(request.user).filter(status=Ad.Status.ACTIVE), pk=pk)
    return content_report_form(
        request, kind=ContentReport.Kind.LISTING, target_id=ad.pk,
        url=ad.get_absolute_url(), label=ad.title, author=ad.author, excerpt=ad.description,
    )


@login_required
@require_http_methods(["GET", "HEAD", "POST"])
@never_cache
def report_chat_message(request, pk):
    item = get_object_or_404(
        CampusMessage.objects.select_related("author", "dormitory").filter(
            Q(dormitory__isnull=True) | Q(dormitory__is_active=True)
        ), pk=pk,
    )
    room = item.dormitory.name if item.dormitory_id else "Общий чат"
    return content_report_form(
        request, kind=ContentReport.Kind.CHAT, target_id=item.pk,
        url=chat_message_url(item, anchor=True), label=f"Сообщение в чате «{room}»",
        author=item.author, excerpt=item.body,
    )


def content_report_form(request, *, kind, target_id, url, label, author, excerpt):
    if author.pk == request.user.pk:
        raise PermissionDenied
    form = ProfileReportForm(request.POST if request.method == "POST" else None)
    if form.is_bound and form.is_valid():
        try:
            ticket, created = report_content(
                user=request.user, kind=kind, target_id=target_id, url=url, label=label,
                author=author, excerpt=excerpt, **form.cleaned_data,
            )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            if created:
                messages.success(request, "Жалоба в очереди модерации. Статус виден в обращении.")
            else:
                messages.info(request, "Вы уже отправили жалобу. Здесь её текущий статус.")
            return redirect(ticket)
    return render(request, "support/content_report.html", {
        "form": form, "target_label": label, "target_url": url, "excerpt": excerpt,
        "heading": "Пожаловаться на объявление" if kind == ContentReport.Kind.LISTING
        else "Пожаловаться на сообщение",
    })


@login_required
@require_http_methods(["GET", "POST"])
@never_cache
def ticket_detail(request, pk):
    ticket = get_object_or_404(tickets_for(request.user), pk=pk)
    form = ReplyForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            reply_ticket(ticket=ticket, actor=request.user, text=form.cleaned_data["text"])
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            return redirect(ticket)
    mark_answers_read(ticket, request.user)
    return render(
        request,
        "support/ticket.html",
        {
            "ticket": ticket,
            "form": form,
            "ticket_messages": ticket.messages.select_related("sender"),
        },
    )


@login_required
@require_POST
def ticket_status(request, pk):
    ticket = get_object_or_404(tickets_for(request.user), pk=pk)
    action = request.POST.get("action")
    if action not in {"close", "reopen"}:
        return HttpResponseBadRequest("Неизвестное действие.")
    set_status(ticket=ticket, actor=request.user, closed=action == "close")
    messages.success(
        request, "Обращение закрыто." if action == "close" else "Обращение снова открыто."
    )
    return redirect(ticket)
