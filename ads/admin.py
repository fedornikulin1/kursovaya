from django.contrib import admin
from .models import Category, Ad

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['id', 'name']

@admin.register(Ad)
class AdAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'category', 'author', 'price', 'created_at', 'is_active', 'image']
    list_filter = ['category', 'is_active']
    search_fields = ['title', 'description']

from .models import Favorite

@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ['user', 'ad', 'created_at']

from .models import Response

@admin.register(Response)
class ResponseAdmin(admin.ModelAdmin):
    list_display = ['user', 'ad', 'created_at', 'text_short']
    
    def text_short(self, obj):
        return obj.text[:50]
    text_short.short_description = 'Text'