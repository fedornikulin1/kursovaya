from django import forms
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from urllib.parse import urlencode
from django.template.loader import render_to_string
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe

from .chat_moderation import validate_campus_chat_body
from .models import CampusMessage, Dormitory


PAGE_SIZE = 50
MAX_MESSAGE_ID = 2**63 - 1


class CampusMessageForm(forms.Form):
    body = forms.CharField(label="Сообщение", max_length=1000)
    kind = forms.ChoiceField(choices=CampusMessage.Kind.choices, required=False)
    reply_to = forms.IntegerField(min_value=1, max_value=MAX_MESSAGE_ID, required=False)

    def clean(self):
        data = super().clean()
        if "body" in data:
            wanted = data.get("kind") == CampusMessage.Kind.WANTED
            try:
                validate_campus_chat_body(data["body"], wanted=wanted)
            except forms.ValidationError as exc:
                self.add_error("body", exc)
        return data

    def clean_reply_to(self):
        reply_id = self.cleaned_data["reply_to"]
        if reply_id is None:
            return None
        reply = CampusMessage.objects.select_related("author").filter(pk=reply_id).first()
        if reply is None:
            raise forms.ValidationError("Сообщение, на которое вы отвечаете, было удалено.")
        return reply


def message_id(value):
    if value.isascii() and value.isdecimal() and len(value) <= 19:
        pk = int(value)
        if pk <= MAX_MESSAGE_ID:
            return pk
    return None


def chat_messages():
    return CampusMessage.objects.select_related("author", "reply_to__author")


def render_messages(request, messages):
    return render_to_string("campus/chat_messages.html", {"chat_messages": messages}, request)


def selected_room(request):
    room = request.GET.get("room", "")
    if not room:
        return None
    room_id = message_id(room)
    if not room_id:
        raise Http404
    return get_object_or_404(Dormitory, pk=room_id, is_active=True)


@never_cache
@login_required
@require_http_methods(["GET", "HEAD", "POST"])
def chat(request):
    posting = request.method == "POST"
    json_post = posting and request.headers.get("Accept") == "application/json"
    room = request.GET.get("room", "")
    dormitory = selected_room(request)
    wanted = request.GET.get("view") == "wanted"
    form = CampusMessageForm(request.POST if posting else None)
    if posting and form.is_valid() and form.cleaned_data["reply_to"] and form.cleaned_data["reply_to"].dormitory_id != (dormitory.pk if dormitory else None):
        form.add_error("reply_to", "Это сообщение находится в другом чате.")
    if posting and form.is_valid():
        message = CampusMessage.objects.create(
            author=request.user,
            dormitory=dormitory,
            body=form.cleaned_data["body"],
            kind=form.cleaned_data["kind"] or CampusMessage.Kind.GENERAL,
            reply_to=form.cleaned_data["reply_to"],
        )
        if json_post:
            visible_in_feed = not wanted or message.kind == CampusMessage.Kind.WANTED
            html = render_messages(request, [message]) if visible_in_feed else ""
            return JsonResponse({"html": html}, status=201)
        url = reverse("campus:chat")
        return redirect(f"{url}?{urlencode({'room': room})}" if room else url)
    if json_post:
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)

    before = message_id(request.GET.get("before", "")) if not posting else None
    around = message_id(request.GET.get("around", "")) if not posting else None
    entries = chat_messages().filter(dormitory=dormitory).order_by("-pk")
    if around:
        entries = entries.filter(pk__lte=around)
        wanted = False
    elif wanted:
        entries = entries.filter(kind=CampusMessage.Kind.WANTED)
    if before:
        entries = entries.filter(pk__lt=before)
    batch = list(entries[: PAGE_SIZE + 1])
    if around and (not batch or batch[0].pk != around):
        raise Http404
    visible = batch[:PAGE_SIZE][::-1]

    reply = form.cleaned_data.get("reply_to") if posting else None
    if not posting and not (before or around):
        reply_id = message_id(request.GET.get("reply", ""))
        if reply_id:
            reply = CampusMessage.objects.select_related("author").filter(pk=reply_id, dormitory=dormitory).first()

    return render(
        request,
        "campus/chat.html",
        {
            "chat_form": form,
            "chat_messages": visible,
            "chat_latest_id": visible[-1].pk if visible else 0,
            "chat_older_id": visible[0].pk if len(batch) > PAGE_SIZE else None,
            "chat_is_archive": bool(before or around),
            "chat_reply": reply,
            "chat_room": dormitory,
            "chat_rooms": Dormitory.objects.filter(is_active=True),
            "chat_wanted": wanted,
        },
        status=400 if posting else 200,
    )


@never_cache
@login_required
@require_safe
def chat_feed(request):
    dormitory = selected_room(request)
    after = message_id(request.GET.get("after", "0"))
    if after is None:
        return JsonResponse({"error": "Некорректный номер сообщения."}, status=400)
    entries = chat_messages().filter(pk__gt=after, dormitory=dormitory)
    if request.GET.get("view") == "wanted":
        entries = entries.filter(kind=CampusMessage.Kind.WANTED)
    batch = list(entries.order_by("pk")[: PAGE_SIZE + 1])
    visible = batch[:PAGE_SIZE]
    return JsonResponse(
        {
            "html": render_messages(request, visible) if visible else "",
            "latest_id": visible[-1].pk if visible else after,
            "has_more": len(batch) > PAGE_SIZE,
        }
    )
