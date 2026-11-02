from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST, require_safe

from .forms import ReplyForm, TicketForm
from .models import FAQ, SupportTicket
from .selectors import tickets_for
from .services import create_ticket, mark_answers_read, reply_ticket, set_status


@require_safe
def help_center(request):
    return render(
        request,
        "support/help.html",
        {"faqs": FAQ.objects.filter(is_published=True), "topics": SupportTicket.Topic.choices},
    )


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
