from django.urls import path
from . import views

app_name = "support"
urlpatterns = [
    path("", views.help_center, name="help"),
    path("tickets/", views.ticket_list, name="tickets"),
    path("tickets/new/", views.ticket_create, name="create"),
    path("tickets/<int:pk>/", views.ticket_detail, name="ticket"),
    path("tickets/<int:pk>/status/", views.ticket_status, name="status"),
]
