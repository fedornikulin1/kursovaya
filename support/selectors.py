from django.db.models import Count, Q

from .models import SupportTicket


def tickets_for(user):
    return (
        SupportTicket.objects.filter(user=user)
        .annotate(
            unread_answers=Count(
                "messages", filter=Q(messages__from_staff=True, messages__read_at__isnull=True)
            )
        )
        .order_by("-updated_at", "-pk")
    )
