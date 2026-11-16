from django.urls import path
from . import views

app_name = "support"
urlpatterns = [
    path("", views.help_center, name="help"),
    path("assistant/", views.ask_assistant, name="ask"),
    path("tickets/", views.ticket_list, name="tickets"),
    path("tickets/new/", views.ticket_create, name="create"),
    path("report/profile/<str:username>/", views.report_profile, name="report_profile"),
    path("report/listing/<int:pk>/", views.report_listing, name="report_listing"),
    path("report/chat/<int:pk>/", views.report_chat_message, name="report_chat_message"),
    path("tickets/<int:pk>/", views.ticket_detail, name="ticket"),
    path("tickets/<int:pk>/status/", views.ticket_status, name="status"),
]
