"""HTML endpoints. Domain mutations delegate to services."""

from django.contrib import messages
from django.conf import settings
from datetime import timedelta
from smtplib import SMTPException
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import ValidationError
from django.db.models import Avg, Case, Count, IntegerField, Q, Value, When
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.vary import vary_on_headers
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST, require_safe, require_http_methods
from django.views.generic import ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView

from .filters import AdFilter
from .forms import AdForm, MessageForm, ProfileForm, RegisterForm, ReviewForm, SettingsForm
from .models import Ad, AdImage, Category, Favorite, Message, Response, Review, SavedSearch
from .selectors import catalogue, conversations, visible_ads, hero_picks
from .services import (
    create_review,
    direct_pair,
    mark_read,
    profile_for,
    save_ad,
    send_message,
    start_conversation,
    start_direct_conversation,
)

User = get_user_model()
SAVED_SEARCH_UNDO_SALT = "ads.saved-search-undo"
SAVED_SEARCH_UNDO_SECONDS = 10


class CampusLoginView(LoginView):
    def get_context_data(self, **kwargs):
        return super().get_context_data(student_access_only=settings.STUDENT_ACCESS_ONLY, **kwargs)


def register(request):
    if settings.STUDENT_ACCESS_ONLY:
        return redirect("login")
    if request.user.is_authenticated:
        return redirect("ads:ad_list")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            user = form.save()
        except (OSError, SMTPException):
            form.add_error(None, "Не удалось отправить письмо. Попробуйте позже.")
        else:
            if settings.EMAIL_VERIFICATION_REQUIRED:
                request.session["pending_confirmation_user"] = user.pk
                return redirect("ads:confirm_email")
            request.session.pop("pending_confirmation_user", None)
            messages.success(request, "Аккаунт создан. Войдите с вашим логином и паролем.")
            return redirect("login")
    return render(request, "registration/register.html", {"form": form})


@never_cache
@require_http_methods(["GET", "POST"])
def confirm_registration_email(request):
    if settings.STUDENT_ACCESS_ONLY:
        raise Http404
    if not settings.EMAIL_VERIFICATION_REQUIRED:
        request.session.pop("pending_confirmation_user", None)
        messages.info(request, "Код из письма больше не нужен. Войдите с вашим логином и паролем.")
        return redirect("login")
    from .email_verification import confirm_email, send_confirmation
    from .models import EmailConfirmation
    user = get_object_or_404(User, pk=request.session.get("pending_confirmation_user"), is_active=False)
    error = ""
    if request.method == "POST":
        if request.POST.get("action") == "resend":
            challenge = EmailConfirmation.objects.filter(user=user).first()
            if challenge and challenge.created_at > timezone.now() - timedelta(seconds=60):
                error = "Повторно запросить код можно через минуту."
            else:
                try:
                    send_confirmation(user)
                    messages.success(request, "Новый код отправлен на почту.")
                except (OSError, SMTPException):
                    error = "Не удалось отправить письмо. Попробуйте позже."
            return render(request, "registration/confirm_email.html", {"email": user.email, "error": error, "mail_is_console": settings.DEBUG and settings.EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend"})
        code = request.POST.get("code", "").strip()
        if len(code) == 6 and code.isascii() and code.isdigit() and confirm_email(user, code):
            request.session.pop("pending_confirmation_user", None)
            messages.success(request, "Почта подтверждена. Теперь можно войти.")
            return redirect("login")
        error = "Неверный или просроченный код. Доступно до пяти попыток."
    return render(request, "registration/confirm_email.html", {"email": user.email, "error": error, "mail_is_console": settings.DEBUG and settings.EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend"})


class AdListView(ListView):
    template_name = "ads/ad_list.html"
    context_object_name = "ads"
    paginate_by = 12

    def get_queryset(self):
        queryset = catalogue(self.request.user).filter(status=Ad.Status.ACTIVE)
        if self.request.GET.get("food") == "1":
            queryset = queryset.filter(category__name="Продукты")
        self.filterset = AdFilter(
            self.request.GET, queryset=queryset
        )
        queryset = self.filterset.qs
        if self.request.user.is_authenticated and not self.request.GET.get("ordering"):
            dormitory_id = getattr(getattr(self.request.user, "profile", None), "dormitory_id", None)
            if dormitory_id:
                queryset = queryset.annotate(nearby=Case(When(dormitory_id=dormitory_id, then=Value(0)), default=Value(1), output_field=IntegerField())).order_by("nearby", "-created_at", "-pk")
        return queryset

    def get_context_data(self, **kwargs):
        from campus.models import Dormitory

        context = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        params.pop("page", None)
        public_ads = catalogue().filter(status=Ad.Status.ACTIVE).order_by()
        context.update(
            filter=self.filterset,
            food_mode=self.request.GET.get("food") == "1",
            dormitories=Dormitory.objects.filter(is_active=True),
            querystring=params.urlencode(),
            categories=Category.objects.filter(is_active=True).annotate(
                active_count=Count("ads", filter=Q(ads__in=public_ads.values("pk")))
            ),
            total_ads=public_ads.count(),
            active_filters_count=sum(
                bool(self.request.GET.get(key))
                for key in (
                    "q",
                    "title",
                    "category",
                    "kind",
                    "price_min",
                    "price_max",
                    "price_type",
                    "dormitory",
                )
            ),
            show_catalog_banner=not any(
                self.request.GET.get(key)
                for key in (
                    "q",
                    "title",
                    "category",
                    "kind",
                    "price_min",
                    "price_max",
                    "price_type",
                    "page",
                    "food",
                    "dormitory",
                )
            ),
        )
        if self.request.user.is_authenticated:
            context.update(saved_search_context(self.request.user, self.filterset.saved_query()))
        return context


def saved_search_context(user, query):
    searches = list(user.saved_searches.all())
    return {
        "saved_query": query,
        "saved_searches": searches,
        "is_saved_search": any(search.query_string == query for search in searches),
    }


def saved_search_fragment(request):
    query = AdFilter(request.GET).saved_query()
    return render_to_string(
        "ads/saved_search_content.html", saved_search_context(request.user, query), request
    )


def _return_to_catalogue(query):
    url = reverse("ads:ad_list")
    if query:
        url = f"{url}?{query}"
    return redirect(f"{url}#catalog-results")


@login_required
@require_POST
def save_search(request):
    filters = AdFilter(request.GET)
    query = filters.saved_query()
    if not query:
        messages.error(request, "Не удалось сохранить поиск. Проверьте параметры фильтров.")
        return redirect("ads:ad_list")
    SavedSearch.objects.get_or_create(
        user=request.user, query_string=query, defaults={"label": filters.saved_label()}
    )
    return _return_to_catalogue(query)


@login_required
@require_POST
def delete_saved_search(request, pk):
    search = get_object_or_404(SavedSearch, pk=pk, user=request.user)
    search.delete()
    if request.headers.get("Accept") == "application/json":
        undo_token = signing.dumps(
            {"user": request.user.pk, "query": search.query_string, "label": search.label},
            salt=SAVED_SEARCH_UNDO_SALT,
        )
        return JsonResponse({
            "html": saved_search_fragment(request),
            "undo_token": undo_token,
            "undo_seconds": SAVED_SEARCH_UNDO_SECONDS,
        })
    return _return_to_catalogue(AdFilter(request.GET).saved_query())


@login_required
@require_POST
def restore_saved_search(request):
    token = request.POST.get("undo_token", "")
    try:
        # Allow a few extra seconds for the restore request to reach the server.
        saved = signing.loads(token, salt=SAVED_SEARCH_UNDO_SALT, max_age=SAVED_SEARCH_UNDO_SECONDS + 5)
    except signing.BadSignature:
        return JsonResponse({"error": "Время на отмену истекло."}, status=400)
    if saved["user"] != request.user.pk:
        return JsonResponse({"error": "Этот поиск принадлежит другому аккаунту."}, status=403)
    restored, _ = SavedSearch.objects.get_or_create(
        user=request.user, query_string=saved["query"], defaults={"label": saved["label"]}
    )
    return JsonResponse({"html": saved_search_fragment(request), "restored_id": restored.pk})


@require_safe
def ad_detail(request, pk):
    ad = get_object_or_404(visible_ads(request.user), pk=pk)
    return render(request, "ads/ad_detail.html", ad_detail_context(request, ad))


def ad_detail_context(request, ad, message_form=None):
    seller_profile = profile_for(ad.author)
    rating = ad.author.reviews_received.aggregate(average=Avg("rating"), count=Count("id"))
    existing = None
    if request.user.is_authenticated and request.user.pk != ad.author_id:
        existing = Response.objects.filter(ad=ad, user=request.user).first()
    return {
        "ad": ad,
        "seller_profile": seller_profile,
        "rating": rating,
        "message_form": message_form if message_form is not None else MessageForm(),
        "existing_conversation": existing,
        "seller_ads_count": Ad.objects.filter(author=ad.author, status="active").count(),
        "can_contact": request.user.is_authenticated
        and request.user.pk != ad.author_id
        and ad.status == "active",
        "recommended_ads": catalogue(request.user)
        .filter(category=ad.category, status="active")
        .exclude(pk=ad.pk)[:4],
    }


@login_required
@require_http_methods(["GET", "POST"])
@never_cache
@vary_on_headers("Accept")
def ad_form(request, pk=None):
    ad = (
        get_object_or_404(Ad, pk=pk, author=request.user)
        if pk
        else Ad(author=request.user, is_study=request.GET.get("study") == "1")
    )
    initial = {}
    if not pk:
        initial["dormitory"] = getattr(getattr(request.user, "profile", None), "dormitory_id", None)
        if request.GET.get("food") == "1":
            initial["category"] = Category.objects.filter(name="Продукты", is_active=True).values_list("pk", flat=True).first()
    form = AdForm(request.POST or None, request.FILES or None, instance=ad, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            save_ad(
                ad=form.save(commit=False),
                author=request.user,
                photos=form.cleaned_data["photos"],
                delete_photos=form.cleaned_data["delete_photos"],
            )
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
        else:
            messages.success(request, "Объявление сохранено.")
            if request.headers.get("Accept") == "application/json":
                return JsonResponse(
                    {"id": ad.pk, "redirect_url": ad.get_absolute_url(), "status": ad.status},
                    status=201 if pk is None else 200,
                )
            return redirect(ad)
    if request.method == "POST" and request.headers.get("Accept") == "application/json":
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
    return render(request, "ads/ad_form.html", {"form": form, "ad": ad})


@login_required
def ad_delete(request, pk):
    ad = get_object_or_404(Ad, pk=pk, author=request.user)
    if request.method == "POST":
        from .services import delete_ad

        try:
            delete_ad(ad=ad, user=request.user)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return redirect(ad)
        messages.success(request, "Объявление удалено.")
        return redirect("ads:my_ads")
    return render(request, "ads/ad_confirm_delete.html", {"ad": ad})


@login_required
@require_POST
def delete_photo(request, pk):
    photo = get_object_or_404(AdImage, pk=pk, ad__author=request.user)
    ad_id = photo.ad_id
    photo.delete()
    return redirect("ads:ad_update", pk=ad_id)


@login_required
@require_POST
def toggle_favorite(request, pk):
    ad = get_object_or_404(visible_ads(request.user), pk=pk)
    favorite, created = Favorite.objects.get_or_create(user=request.user, ad=ad)
    if not created:
        favorite.delete()
    if request.headers.get("Accept") == "application/json":
        return JsonResponse({"is_favorite": created})
    return redirect(ad)


class FavoriteListView(LoginRequiredMixin, ListView):
    template_name = "ads/favorite_list.html"
    context_object_name = "ads"
    paginate_by = 12

    def get_queryset(self):
        return catalogue(self.request.user).filter(
            favorited_by__user=self.request.user, status="active"
        )


class MyAdsListView(LoginRequiredMixin, ListView):
    template_name = "ads/my_ads.html"
    context_object_name = "ads"
    paginate_by = 12

    def get_queryset(self):
        return catalogue(self.request.user, include_own_hidden=True).filter(author=self.request.user)


@login_required
@require_POST
def contact_seller(request, pk):
    ad = get_object_or_404(visible_ads(request.user), pk=pk)
    form = MessageForm(request.POST)
    if form.is_valid():
        try:
            conversation = start_conversation(
                ad=ad, user=request.user, text=form.cleaned_data["text"]
            )
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        else:
            return redirect("ads:conversation", pk=conversation.pk)
    else:
        return render(
            request, "ads/ad_detail.html", ad_detail_context(request, ad, form), status=400
        )
    return redirect(ad)


@login_required
@require_safe
@never_cache
@vary_on_headers("X-Messenger-Request")
def inbox(request):
    context = messenger_context(request.user)
    template = (
        "components/messenger.html"
        if request.headers.get("X-Messenger-Request") == "true"
        else "ads/inbox.html"
    )
    return render(request, template, context)


def messenger_context(user, thread=None, form=None):
    from campus.views import meeting_context

    threads = list(conversations(user, include_direct=True))
    for item in threads:
        item.other_user = item.other_participant(user)
        item.last_activity = item.last_message_at or item.updated_at
    return {
        "threads": threads,
        "thread": thread,
        "thread_count": len(threads),
        "unread_thread_count": sum(item.unread_count > 0 for item in threads),
        "other_user": thread.other_participant(user) if thread else None,
        "chat_messages": thread.messages.select_related("sender", "offered_ad") if thread else [],
        "form": form if form is not None else MessageForm(),
        "display_timezone": timezone.get_current_timezone_name(),
        **(meeting_context(user, thread) if thread and thread.ad_id else {}),
    }


@login_required
@require_safe
@never_cache
def inbox_sidebar(request):
    context = messenger_context(request.user)
    active = request.GET.get("active", "")
    selected = next((item for item in context["threads"] if str(item.pk) == active), None)
    context["thread"] = selected
    read_ids = (
        list(
            selected.messages.filter(sender=request.user, read_at__isnull=False)
            .order_by("-pk")
            .values_list("pk", flat=True)[:100]
        )
        if selected
        else []
    )
    return JsonResponse(
        {
            "html": render_to_string("components/thread_items.html", context, request=request),
            "count": context["thread_count"],
            "unread_threads": context["unread_thread_count"],
            "unread_total": sum(item.unread_count for item in context["threads"]),
            "read_ids": read_ids,
        }
    )


@login_required
@never_cache
@vary_on_headers("X-Messenger-Request")
@require_http_methods(["GET", "POST"])
def conversation(request, pk):
    thread = get_object_or_404(conversations(request.user, include_direct=True), pk=pk)
    form = MessageForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        send_message(conversation=thread, sender=request.user, text=form.cleaned_data["text"])
        return redirect("ads:conversation", pk=thread.pk)
    mark_read(thread, request.user)
    context = messenger_context(request.user, thread, form)
    template = (
        "components/messenger.html"
        if request.headers.get("X-Messenger-Request") == "true"
        else "ads/conversation.html"
    )
    return render(request, template, context, status=400 if request.method == "POST" else 200)


@login_required
@never_cache
@require_http_methods(["GET", "HEAD", "POST"])
def profile_message(request, username):
    recipient = get_object_or_404(
        User.objects.exclude(pk=request.user.pk), username=username, is_active=True
    )
    posting = request.method == "POST"
    form = MessageForm(request.POST if posting else None)
    if posting:
        if form.is_valid():
            thread = start_direct_conversation(
                user=request.user, recipient=recipient, text=form.cleaned_data["text"]
            )
            return redirect("ads:conversation", pk=thread.pk)
    else:
        thread = Response.objects.filter(ad=None, **direct_pair(request.user, recipient)).first()
        if thread:
            return redirect("ads:conversation", pk=thread.pk)
    return render(
        request,
        "ads/profile_message.html",
        {"recipient": recipient, "form": form},
        status=400 if posting else 200,
    )


@login_required
@require_POST
def accept_response(request, pk):
    thread = get_object_or_404(Response, pk=pk, ad__author=request.user)
    thread.is_accepted = True
    thread.save(update_fields=["is_accepted", "updated_at"])
    messages.success(request, "Отклик принят. Теперь участники могут оставить друг другу отзыв.")
    return redirect("ads:conversation", pk=pk)


@login_required
@require_http_methods(["GET", "POST"])
def edit_profile(request):
    profile = profile_for(request.user)
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            try:
                form.save()
            except ValidationError as exc:
                for field, errors in exc.message_dict.items():
                    form.add_error(field, errors)
            else:
                messages.success(request, "Профиль обновлён.")
                return redirect("ads:user_profile", username=request.user.username)
    else:
        form = ProfileForm(instance=profile)
    return render(request, "ads/profile_form.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def account_settings(request):
    form = SettingsForm(
        request.POST if request.method == "POST" else None, instance=profile_for(request.user)
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Настройки сохранены.")
        return redirect("ads:settings")
    return render(request, "ads/settings.html", {"form": form})


@require_safe
def information(request, page):
    from .information import PAGES

    if page not in PAGES:
        from django.http import Http404

        raise Http404
    return render(request, "ads/information.html", {"page": PAGES[page]})


def user_profile(request, username):
    user = get_object_or_404(User, username=username, is_active=True)
    reviews = user.reviews_received.select_related("from_user")
    return render(
        request,
        "ads/user_profile.html",
        {
            "profile_user": user,
            "profile": profile_for(user),
            "reviews": reviews,
            "rating": reviews.aggregate(average=Avg("rating"), count=Count("id")),
            "ads": catalogue(request.user).filter(author=user, status="active"),
            "review_form": ReviewForm(),
        },
    )


@login_required
def add_review(request, username):
    recipient = get_object_or_404(User, username=username, is_active=True)
    form = ReviewForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            create_review(author=request.user, recipient=recipient, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
        else:
            messages.success(request, "Спасибо за отзыв!")
            return redirect("ads:user_profile", username=username)
    return render(request, "ads/add_review.html", {"form": form, "to_user": recipient})
