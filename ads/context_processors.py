from django.db.models import Q
from .models import Message
from .services import profile_for


def navigation(request):
    unread = 0
    profile = None
    if request.user.is_authenticated:
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
        "account_profile": profile,
        "reduce_motion": bool(profile and profile.reduce_motion),
    }
