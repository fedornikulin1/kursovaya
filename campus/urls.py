from django.urls import path
from . import views

app_name = "campus"
urlpatterns = [
    path("", views.exchange, name="exchange"),
    path("requests/new/", views.request_form, name="request_create"),
    path("requests/<int:pk>/", views.request_detail, name="request_detail"),
    path("requests/<int:pk>/edit/", views.request_form, name="request_edit"),
    path("requests/<int:pk>/offer/", views.offer_request, name="offer_request"),
    path("conversations/<int:pk>/meeting/", views.meeting_propose, name="meeting_propose"),
    path("meetings/<int:pk>/action/", views.meeting_update, name="meeting_update"),
]
