"""Deterministic recommendations: exact subjects and shared words, with reasons."""

import re
import unicodedata
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from ads.models import Ad
from ads.selectors import catalogue
from .models import Meeting


def normalized(value):
    return " ".join(
        re.findall(r"[\w]+", unicodedata.normalize("NFKC", value).casefold().replace("ё", "е"))
    )


def search_study(queryset, value, fields=("title", "subject")):
    """Use Unicode casefold in SQLite too; preserve ordering and annotations."""
    needle = normalized(value)
    ids = [
        row[0]
        for row in queryset.values_list("pk", *fields)
        if any(needle in normalized(text) for text in row[1:])
    ]
    return queryset.filter(pk__in=ids)


def study_offers(user=None):
    occupied = Meeting.objects.filter(ad_id=OuterRef("pk")).filter(
        Q(status__in=["transferred", "on_loan", "return_pending"])
        | Q(status="confirmed", ends_at__gt=timezone.now())
    )
    return (
        catalogue(user)
        .filter(is_study=True, status=Ad.Status.ACTIVE)
        .exclude(kind__in=[Ad.Kind.BUY, Ad.Kind.ROOMMATE])
        .select_related("campus_place")
        .annotate(campus_reserved=Exists(occupied))
    )


def ranked_matches(study_request, user=None, limit=24):
    query = (
        study_offers(user).exclude(author_id=study_request.author_id).filter(campus_reserved=False)
    )
    modes = {"buy": "sell", "exchange": "exchange", "give": "give", "lend": "lend"}
    if study_request.mode != "any":
        if study_request.mode == "give":
            query = query.filter(Q(kind="give") | Q(kind="sell", price_type="free"))
        else:
            query = query.filter(kind=modes[study_request.mode])
    target = normalized(study_request.subject)
    stop_words = {"и", "по", "в", "на", "для", "с", "со", "к"}
    tokens = set(target.split()) - stop_words
    # Python casefold is deliberate: SQLite's iexact does not fold Cyrillic case.
    # This initial version ranks all eligible offers in O(n), without a hidden candidate cap.
    results = []
    for ad in query:
        candidate = normalized(ad.subject)
        candidate_tokens = set(candidate.split()) - stop_words
        overlap = len(tokens & candidate_tokens) / max(len(tokens), len(candidate_tokens), 1)
        if target == candidate:
            score, reasons = 60, ["Тот же предмет"]
        elif overlap >= 0.5:
            score, reasons = 40, ["Похожий предмет"]
        else:
            continue
        if study_request.course and study_request.course == ad.course:
            score += 15
            reasons.append("Ваш курс")
        if study_request.semester and study_request.semester == ad.semester:
            score += 10
            reasons.append("Тот же семестр")
        if study_request.place_id and study_request.place_id == ad.campus_place_id:
            score += 10
            reasons.append("Удобное вам место")
        if ad.available_until and ad.available_until <= timezone.now():
            continue
        if study_request.available_from and ad.available_from:
            if max(study_request.available_from, ad.available_from, timezone.now()) < min(
                study_request.available_until, ad.available_until
            ):
                score += 5
                reasons.append("Совпадает время встречи")
        results.append({"ad": ad, "score": score, "reasons": reasons})
    results.sort(key=lambda item: (-item["score"], -item["ad"].pk))
    return results[:limit]
