"""Reusable database queries; the API and website see the same catalogue."""

from django.db.models import Count, Exists, OuterRef, Q, Subquery, Value, IntegerField
from django.db.models.functions import Coalesce
from .models import Ad, Favorite, Message, Response


def catalogue(user=None):
    queryset = Ad.objects.select_related("category", "author").prefetch_related("images")
    if user is not None and user.is_authenticated:
        queryset = queryset.annotate(
            is_favorite=Exists(Favorite.objects.filter(user=user, ad_id=OuterRef("pk")))
        )
    return queryset


def visible_ads(user):
    condition = Q(status=Ad.Status.ACTIVE)
    if user.is_authenticated:
        condition |= Q(author=user)
    return catalogue(user).filter(condition)


def hero_picks(user, limit=6):
    """A small, varied set of real published listings, without duplicate covers."""
    candidates = list(
        catalogue(user)
        .filter(status=Ad.Status.ACTIVE)
        .exclude(image="")
        .order_by("-created_at", "-pk")[:80]
    )
    result, images, categories = [], set(), set()
    for varied in (True, False):
        for ad in candidates:
            if ad.image.name in images or (varied and ad.category_id in categories):
                continue
            result.append(ad)
            images.add(ad.image.name)
            categories.add(ad.category_id)
            if len(result) == limit:
                return result
    return result


def conversations(user):
    latest = Message.objects.filter(response_id=OuterRef("pk")).order_by("-created_at", "-pk")
    unread = (
        Message.objects.filter(response_id=OuterRef("pk"), read_at__isnull=True)
        .exclude(sender=user)
        .values("response_id")
        .annotate(total=Count("pk"))
        .values("total")
    )
    return (
        Response.objects.filter(Q(user=user) | Q(ad__author=user))
        .select_related("ad", "ad__author", "user")
        .prefetch_related("ad__images")
        .annotate(
            last_message_text=Subquery(latest.values("text")[:1]),
            last_sender_id=Subquery(latest.values("sender_id")[:1]),
            last_message_at=Subquery(latest.values("created_at")[:1]),
            unread_count=Coalesce(Subquery(unread, output_field=IntegerField()), Value(0)),
        )
    )
