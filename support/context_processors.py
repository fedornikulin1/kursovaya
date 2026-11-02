from .models import SupportMessage


def notifications(request):
    unread = 0
    if request.user.is_authenticated:
        unread = SupportMessage.objects.filter(
            ticket__user=request.user, from_staff=True, read_at__isnull=True
        ).count()
    return {"unread_support_answers": unread}
