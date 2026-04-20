from django.urls import path
from . import views

app_name = 'ads'

urlpatterns = [
    path('', views.AdListView.as_view(), name='ad_list'),
    path('ad/<int:pk>/', views.AdDetailView.as_view(), name='ad_detail'),
    path('ad/create/', views.AdCreateView.as_view(), name='ad_create'),
    path('register/', views.register, name='register'),
    path('ad/<int:pk>/favorite/', views.toggle_favorite, name='toggle_favorite'),
    path('favorites/', views.FavoriteListView.as_view(), name='favorite_list'),
    path('my-ads/', views.MyAdsListView.as_view(), name='my_ads'),
    path('ad/<int:pk>/update/', views.AdUpdateView.as_view(), name='ad_update'),
    path('ad/<int:pk>/delete/', views.AdDeleteView.as_view(), name='ad_delete'),
    path('response/<int:pk>/accept/', views.accept_response, name='accept_response'),
    path('response/<int:pk>/decline/', views.decline_response, name='decline_response'),
    path('response/<int:pk>/reply/', views.reply_to_response, name='reply_to_response'),
]