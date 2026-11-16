from urllib.parse import parse_qsl

from django.db.models import Exists, OuterRef, Q

from .filters import AdFilter
from .models import Ad, Notification
from .selectors import catalogue


def visible_notifications(user):
    listings = catalogue().filter(status=Ad.Status.ACTIVE).order_by().values("pk")
    return Notification.objects.filter(user=user).filter(
        Q(listing__isnull=True) | Q(listing_id__in=listings)
    )


def sync_saved_search_notifications(user):
    searches = list(user.saved_searches.only("query_string", "created_at"))
    if not searches:
        return

    available = catalogue().filter(status=Ad.Status.ACTIVE).exclude(author=user).order_by()
    matches = Q()
    for search in searches:
        filters = AdFilter(dict(parse_qsl(search.query_string)), queryset=available)
        if filters.is_valid():
            results = filters.qs.filter(published_at__gte=search.created_at).order_by()
            matches |= Q(pk__in=results.values("pk"))
    if not matches:
        return

    recorded = Notification.objects.filter(user=user, listing_id=OuterRef("pk"))
    new_listings = available.filter(matches).filter(~Exists(recorded))
    Notification.objects.bulk_create(
        [
            Notification(user=user, kind=Notification.Kind.SEARCH, listing_id=pk, created_at=published)
            for pk, published in new_listings.values_list("pk", "published_at")
        ],
        batch_size=200, ignore_conflicts=True,
    )
