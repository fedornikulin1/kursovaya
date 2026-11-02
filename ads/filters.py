import django_filters
from django.db.models import Q
from .models import Ad, Category


class AdFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(method="search", label="Поиск")
    title = django_filters.CharFilter(field_name="title", lookup_expr="icontains", label="Название")
    category = django_filters.ModelChoiceFilter(
        queryset=Category.objects.filter(is_active=True), empty_label="Все категории"
    )
    price_min = django_filters.NumberFilter(field_name="price", lookup_expr="gte", min_value=0)
    price_max = django_filters.NumberFilter(field_name="price", lookup_expr="lte", min_value=0)
    kind = django_filters.ChoiceFilter(choices=Ad.Kind.choices)
    price_type = django_filters.ChoiceFilter(choices=Ad.PriceType.choices)
    is_study = django_filters.BooleanFilter()
    subject = django_filters.CharFilter(method="search_subject")
    course = django_filters.NumberFilter()
    semester = django_filters.NumberFilter()
    campus_place = django_filters.NumberFilter()
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

    def search_subject(self, queryset, name, value):
        from campus.selectors import search_study

        return search_study(queryset, value, fields=("subject",))
