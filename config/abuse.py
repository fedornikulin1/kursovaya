from time import time

from django.core.cache import cache
from django.http import JsonResponse
from rest_framework.exceptions import AuthenticationFailed


# Rates apply across rooms and web/API entry points, per account.
WRITE_ROUTES = {
    "campus:chat": ("campus-chat", 12, 60, 16 * 1024),
    "ads:ad_create": ("new-ad", 8, 3600, None),
    "api-ad-list": ("new-ad", 8, 3600, None),
    "ads:ad_update": ("edit-ad", 30, 60, None),
    "api-ad-detail": ("edit-ad", 30, 60, None),
    "api-ad-photos": ("edit-ad", 30, 60, None),
    "ads:contact_seller": ("direct-message", 30, 60, 64 * 1024),
    "ads:conversation": ("direct-message", 30, 60, 64 * 1024),
    "ads:profile_message": ("direct-message", 30, 60, 64 * 1024),
    "campus:offer_wanted": ("direct-message", 30, 60, 64 * 1024),
    "campus:close_wanted": ("campus-request-status", 30, 60, 16 * 1024),
    "api-conversation-list": ("direct-message", 30, 60, 64 * 1024),
    "api-conversation-messages": ("direct-message", 30, 60, 64 * 1024),
    "campus:request_create": ("new-ad", 8, 3600, 64 * 1024),
    "campus-request-list": ("new-ad", 8, 3600, 64 * 1024),
    "campus:request_edit": ("edit-ad", 30, 60, 64 * 1024),
    "campus-request-detail": ("edit-ad", 30, 60, 64 * 1024),
    "support:ask": ("support-assistant", 5, 60, 16 * 1024),
    "support:create": ("support-ticket", 8, 3600, 64 * 1024),
    "support:report_profile": ("support-ticket", 8, 3600, 64 * 1024),
    "support:report_listing": ("support-ticket", 8, 3600, 64 * 1024),
    "support:report_chat_message": ("support-ticket", 8, 3600, 64 * 1024),
    "support-ticket-list": ("support-ticket", 8, 3600, 64 * 1024),
}


def take_request_slot(scope, identity, limit, seconds):
    window, elapsed = divmod(int(time()), seconds)
    remaining = seconds - elapsed
    key = f"write-limit:{scope}:{identity}:{window}"
    if cache.add(key, 1, timeout=remaining + 1):
        return 0
    try:
        count = cache.incr(key)
    except ValueError:
        # A cache eviction between add and increment may remove the counter.
        return 0 if cache.add(key, 1, timeout=remaining + 1) else remaining
    return remaining if count > limit else 0


class WriteLimitsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view, args, kwargs):
        rule = WRITE_ROUTES.get(request.resolver_match.view_name)
        if not rule or request.method not in {"POST", "PUT", "PATCH"}:
            return None
        scope, limit, seconds, max_bytes = rule
        try:
            size = int(request.META.get("CONTENT_LENGTH") or 0)
        except ValueError:
            return JsonResponse({"detail": "Некорректный размер запроса."}, status=400)
        if max_bytes and size > max_bytes:
            return JsonResponse({"detail": "Запрос слишком большой."}, status=413)

        user = request.user
        if request.path_info.startswith("/api/v1/"):
            from ads.authentication import CampusJWTAuthentication

            try:
                jwt = CampusJWTAuthentication().authenticate(request)
            except AuthenticationFailed:
                # Let DRF return its standard token error.
                return None
            if jwt:
                user = jwt[0]
        if not user.is_authenticated:
            return None
        wait = take_request_slot(scope, user.pk, limit, seconds)
        if wait:
            detail = "Слишком много действий. Подождите и попробуйте снова."
            errors = {"__all__": [{"message": detail, "code": "rate_limited"}]}
            return JsonResponse(
                {"detail": detail, "errors": errors},
                status=429,
                headers={"Retry-After": str(wait)},
            )
        return None
