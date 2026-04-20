import django_filters
from .models import Ad, Category

class AdFilter(django_filters.FilterSet):
    title = django_filters.CharFilter(lookup_expr='icontains', label='Поиск по названию')
    category = django_filters.ModelChoiceFilter(
        queryset=Category.objects.all(),
        label='Категория',
        empty_label='Все категории'
    )
    price_min = django_filters.NumberFilter(field_name='price', lookup_expr='gte', label='Цена от')
    price_max = django_filters.NumberFilter(field_name='price', lookup_expr='lte', label='Цена до')

    class Meta:
        model = Ad
        fields = ['title', 'category']