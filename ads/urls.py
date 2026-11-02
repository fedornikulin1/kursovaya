from django.urls import path
from . import views

app_name = "ads"
urlpatterns = [
    path("", views.AdListView.as_view(), name="ad_list"),
    path("register/", views.register, name="register"),
    path("ad/create/", views.ad_form, name="ad_create"),
    path("ad/<int:pk>/", views.ad_detail, name="ad_detail"),
    path("ad/<int:pk>/update/", views.ad_form, name="ad_update"),
    path("ad/<int:pk>/delete/", views.ad_delete, name="ad_delete"),
    path("ad/<int:pk>/favorite/", views.toggle_favorite, name="toggle_favorite"),
    path("ad/<int:pk>/contact/", views.contact_seller, name="contact_seller"),
    path("photos/<int:pk>/delete/", views.delete_photo, name="delete_photo"),
    path("favorites/", views.FavoriteListView.as_view(), name="favorite_list"),
    path("my-ads/", views.MyAdsListView.as_view(), name="my_ads"),
    path("messages/", views.inbox, name="inbox"),
    path("messages/sidebar/", views.inbox_sidebar, name="inbox_sidebar"),
    path("messages/<int:pk>/", views.conversation, name="conversation"),
    path("response/<int:pk>/accept/", views.accept_response, name="accept_response"),
    path("profile/edit/", views.edit_profile, name="edit_profile"),
    path("settings/", views.account_settings, name="settings"),
    path("info/<slug:page>/", views.information, name="information"),
    path("user/<str:username>/", views.user_profile, name="user_profile"),
    path("user/<str:username>/review/", views.add_review, name="add_review"),
]
