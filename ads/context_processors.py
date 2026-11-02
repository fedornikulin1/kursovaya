from django.db.models import Q
from .models import Message
from .services import profile_for


def navigation(request):
    unread = 0
    if request.user.is_authenticated:
        unread = (
            Message.objects.filter(
                Q(response__user=request.user) | Q(response__ad__author=request.user),
                read_at__isnull=True,
            )
            .exclude(sender=request.user)
            .count()
        )
    return {
        "unread_messages": unread,
        "reduce_motion": request.user.is_authenticated and profile_for(request.user).reduce_motion,
    }
