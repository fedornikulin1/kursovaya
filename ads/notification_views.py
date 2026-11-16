from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_safe

from .models import Notification
from .notifications import sync_saved_search_notifications, visible_notifications


@login_required
@never_cache
@require_safe
def inbox(request):
    sync_saved_search_notifications(request.user)
    entries = visible_notifications(request.user).select_related("listing__dormitory")
    page = Paginator(entries, 25).get_page(request.GET.get("page"))
    return render(request, "ads/notifications.html", {"page_obj": page})


@login_required
@never_cache
@require_safe
def count(request):
    if request.method == "GET":
        sync_saved_search_notifications(request.user)
    unread = visible_notifications(request.user).filter(read_at__isnull=True).count()
    return JsonResponse({"unread": unread})


@login_required
@never_cache
@require_POST
def open_notification(request, pk):
    entries = visible_notifications(request.user)
    item = get_object_or_404(entries.select_related("message"), pk=pk)
    entries.filter(pk=item.pk, read_at__isnull=True).update(read_at=timezone.now())
    return redirect(item.get_absolute_url())


@login_required
@never_cache
@require_POST
def read_all(request):
    sync_saved_search_notifications(request.user)
    Notification.objects.filter(user=request.user, read_at__isnull=True).update(read_at=timezone.now())
    return redirect("ads:notifications")
