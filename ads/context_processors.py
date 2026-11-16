from django.db.models import Q
from .models import Message
from .notifications import visible_notifications
from .services import profile_for


def navigation(request):
    unread = 0
    unread_updates = 0
    profile = None
    if request.user.is_authenticated:
        unread_updates = visible_notifications(request.user).filter(read_at__isnull=True).count()
        profile = profile_for(request.user)
        unread = (
            Message.objects.filter(
                Q(response__user=request.user)
                | Q(response__ad__author=request.user)
                | Q(response__direct_peer=request.user),
                read_at__isnull=True,
            )
            .exclude(sender=request.user)
            .count()
        )
    return {
        "unread_messages": unread,
        "unread_board_notifications": unread_updates,
        "account_profile": profile,
        "reduce_motion": bool(profile and profile.reduce_motion),
    }
