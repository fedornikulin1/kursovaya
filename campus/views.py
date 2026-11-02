from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.db.models import Q
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST, require_safe
from django.db import transaction

from ads.models import Response
from ads.selectors import conversations
from ads.services import send_message
from .forms import MeetingForm, StudyRequestForm
from .models import CampusPlace, Meeting, StudyRequest
from .selectors import ranked_matches, study_offers, search_study
from .services import meeting_action, propose_meeting, respond_to_request


@require_safe
def exchange(request):
    tab = request.GET.get("tab", "offers")
    if tab not in ("offers", "requests", "mine"):
        tab = "offers"
    query = study_offers(request.user)
    search = request.GET.get("q", "").strip()[:120]
    if search:
        query = search_study(query, search)
    mode = request.GET.get("mode", "")
    if mode in ("sell", "exchange", "give", "lend"):
        query = query.filter(kind=mode)
    place = request.GET.get("place", "")
    if place.isdecimal():
        query = query.filter(campus_place_id=int(place))
    needs = StudyRequest.objects.select_related("author", "place").filter(is_active=True)
    if search:
        needs = search_study(needs, search)
    if place.isdecimal():
        needs = needs.filter(place_id=int(place))
    mine, meetings = [], []
    if tab == "mine":
        if not request.user.is_authenticated:
            return redirect("/accounts/login/?next=/campus/%3Ftab%3Dmine")
        mine = StudyRequest.objects.filter(author=request.user).select_related("place")
        meetings = (
            Meeting.objects.filter(Q(conversation__user=request.user) | Q(ad__author=request.user))
            .select_related("ad", "place", "conversation")
            .order_by("-created_at")[:30]
        )
    page = Paginator(needs if tab == "requests" else query, 12).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(
        request,
        "campus/exchange.html",
        {
            "tab": tab,
            "page_obj": page,
            "places": CampusPlace.objects.filter(is_active=True),
            "mine": mine,
            "meetings": meetings,
            "offer_count": study_offers(request.user).count(),
            "request_count": StudyRequest.objects.filter(is_active=True).count(),
            "querystring": params.urlencode(),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def request_form(request, pk=None):
    need = (
        get_object_or_404(StudyRequest, pk=pk, author=request.user)
        if pk
        else StudyRequest(author=request.user)
    )
    form = StudyRequestForm(request.POST if request.method == "POST" else None, instance=need)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(
            request, "Запрос сохранён. Подходящие предложения появятся на его странице."
        )
        return redirect(need)
    return render(request, "campus/request_form.html", {"form": form, "need": need})


@require_safe
def request_detail(request, pk):
    visible = Q(is_active=True)
    if request.user.is_authenticated:
        visible |= Q(author=request.user)
    need = get_object_or_404(
        StudyRequest.objects.select_related("author", "place").filter(visible), pk=pk
    )
    own = request.user.pk == need.author_id
    offers = (
        study_offers(request.user).filter(author=request.user)
        if request.user.is_authenticated and not own
        else []
    )
    return render(
        request,
        "campus/request_detail.html",
        {
            "need": need,
            "own": own,
            "matches": ranked_matches(need, request.user) if own and need.is_active else [],
            "own_offers": offers,
        },
    )


@login_required
@require_POST
@transaction.atomic
def offer_request(request, pk):
    need = get_object_or_404(StudyRequest, pk=pk, is_active=True)
    ad = get_object_or_404(
        study_offers(request.user),
        pk=request.POST.get("ad") if request.POST.get("ad", "").isdecimal() else 0,
        author=request.user,
    )
    if need.author_id == request.user.pk:
        messages.error(request, "Это ваш запрос.")
        return redirect(need)
    try:
        thread = respond_to_request(study_request=need, ad=ad, user=request.user)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
        return redirect(need)
    return redirect("ads:conversation", pk=thread.pk)


def meeting_context(user, thread, form=None):
    meetings = list(thread.meetings.select_related("place").order_by("-created_at")[:8])
    active = next(
        (item for item in meetings if item.effective_status in ["proposed", *Meeting.LIVE]), None
    )
    for item in meetings:
        state = item.effective_status
        seller = user.pk == thread.ad.author_id
        item.can_confirm = state == "proposed" and item.proposed_by_id != user.pk
        item.can_cancel = state in ("proposed", "confirmed")
        item.can_handover = seller and state == "confirmed" and item.starts_at <= timezone.now()
        item.can_receive = not seller and state == "transferred"
        item.can_return = not seller and state == "on_loan"
        item.can_finish_return = seller and state == "return_pending"
    revision = "|".join(
        f"{m.pk}:{m.effective_status}:{int(m.can_handover)}:{int(m.is_overdue)}" for m in meetings
    )
    return {
        "meeting_thread": thread,
        "campus_meetings": meetings,
        "active_meeting": active,
        "meeting_form": form if form is not None else MeetingForm(conversation=thread),
        "meeting_revision": revision,
        "meeting_timezone": timezone.get_current_timezone_name(),
    }


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def meeting_propose(request, pk):
    thread = get_object_or_404(conversations(request.user), pk=pk)
    form = MeetingForm(request.POST if request.method == "POST" else None, conversation=thread)
    if request.method == "POST" and form.is_valid():
        try:
            propose_meeting(conversation=thread, user=request.user, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
        else:
            return redirect("ads:conversation", pk=pk)
    context = meeting_context(request.user, thread, form)
    if request.method == "GET":
        return JsonResponse(
            {
                "revision": context["meeting_revision"],
                "html": render_to_string("campus/meeting_panel.html", context, request=request),
            }
        )
    context["meeting_expanded"] = True
    return render(request, "campus/meeting_form.html", context, status=400)


@login_required
@require_POST
def meeting_update(request, pk):
    meeting = get_object_or_404(
        Meeting.objects.filter(Q(conversation__user=request.user) | Q(ad__author=request.user)),
        pk=pk,
    )
    try:
        meeting_action(meeting=meeting, user=request.user, action=request.POST.get("action"))
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect("ads:conversation", pk=meeting.conversation_id)
