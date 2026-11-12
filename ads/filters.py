from decimal import Decimal
from urllib.parse import urlencode

import django_filters
from django.db.models import Q
from django.utils.text import Truncator

from .models import Ad, Category, SavedSearch


class AdFilter(django_filters.FilterSet):
    food = django_filters.ChoiceFilter(
        choices=(("1", "Продукты"),), method="filter_food", empty_label="Все объявления"
    )
    q = django_filters.CharFilter(method="search", label="Поиск")
    title = django_filters.CharFilter(field_name="title", lookup_expr="icontains", label="Название")
    category = django_filters.ModelChoiceFilter(
        queryset=Category.objects.filter(is_active=True), empty_label="Все категории"
    )
    price_min = django_filters.NumberFilter(field_name="price", lookup_expr="gte", min_value=0)
    price_max = django_filters.NumberFilter(field_name="price", lookup_expr="lte", min_value=0)
    kind = django_filters.ChoiceFilter(choices=Ad.Kind.choices, empty_label="Все типы")
    price_type = django_filters.ChoiceFilter(choices=Ad.PriceType.choices, empty_label="Любая цена")
    is_study = django_filters.BooleanFilter()
    subject = django_filters.CharFilter(method="search_subject")
    course = django_filters.NumberFilter()
    semester = django_filters.NumberFilter()
    campus_place = django_filters.NumberFilter()
    dormitory = django_filters.CharFilter(method="filter_dormitory")
    ordering = django_filters.OrderingFilter(
        fields=(("created_at", "date"), ("price", "price")),
        field_labels={"created_at": "Дата", "price": "Цена"},
    )

    class Meta:
        model = Ad
        fields = ["q", "category", "kind", "price_type"]

    def search(self, queryset, name, value):
        return queryset.filter(
            Q(title__icontains=value)
            | Q(description__icontains=value)
            | Q(location__icontains=value)
        )

    def filter_food(self, queryset, name, value):
        return queryset.filter(category__name="Продукты")

    def filter_dormitory(self, queryset, name, value):
        if value == "outside":
            return queryset.filter(dormitory__isnull=True)
        if value.isascii() and value.isdecimal() and len(value) <= 10:
            return queryset.filter(dormitory_id=int(value))
        return queryset.none()

    def search_subject(self, queryset, name, value):
        from campus.selectors import search_study

        return search_study(queryset, value, fields=("subject",))

    def saved_query(self):
        """Serialize validated filter values rather than an arbitrary request URL."""
        if not self.is_valid():
            return ""
        values = {}
        for key, value in self.form.cleaned_data.items():
            if value in (None, "", []):
                continue
            if key == "category":
                value = value.pk
            elif key == "ordering":
                if value == ["-date"]:
                    continue
                value = ",".join(value)
            elif isinstance(value, bool):
                value = str(value).lower()
            elif isinstance(value, Decimal):
                value = str(value) if value else "0"
                if "." in value and "E" not in value:
                    value = value.rstrip("0").rstrip(".")
            values[key] = value
        query = urlencode(sorted(values.items()))
        return query if len(query) <= SavedSearch.MAX_QUERY_LENGTH else ""

    def saved_label(self):
        data = self.form.cleaned_data
        search = data.get("q") or data.get("title") or data.get("subject")
        parts = [
            Truncator(search).chars(65) if search else "",
            "Продукты" if data.get("food") else "",
            str(data["category"]) if data.get("category") else "",
            Ad.Kind(data["kind"]).label if data.get("kind") else "",
        ]
        for key, prefix in (("price_min", "от"), ("price_max", "до")):
            if data.get(key) is not None:
                parts.append(f"{prefix} {data[key]:g} ₽")
        if data.get("price_type"):
            parts.append(Ad.PriceType(data["price_type"]).label)
        if data.get("ordering") and data["ordering"] != ["-date"]:
            ordering_labels = {
                "price": "сначала дешевле",
                "-price": "сначала дороже",
                "date": "сначала старые",
                "-date": "сначала новые",
            }
            parts.append(ordering_labels[data["ordering"][0]])
        label = " · ".join(part for part in parts if part) or "Поиск по учебным параметрам"
        return Truncator(label).chars(SavedSearch._meta.get_field("label").max_length)
