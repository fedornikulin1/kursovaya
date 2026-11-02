from django.urls import include, path
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("ads", views.AdViewSet, basename="api-ad")
router.register("categories", views.CategoryViewSet, basename="api-category")
router.register("conversations", views.ConversationViewSet, basename="api-conversation")
router.register("reviews", views.ReviewViewSet, basename="api-review")
urlpatterns = [
    path("", include(router.urls)),
    path("auth/register/", views.RegisterView.as_view()),
    path("auth/token/", views.LoginView.as_view()),
    path("auth/token/refresh/", views.RefreshView.as_view()),
    path("auth/logout/", views.LogoutView.as_view()),
    path("me/", views.MeView.as_view()),
    path("users/<str:username>/", views.PublicProfileView.as_view()),
    path("photos/<int:pk>/", views.PhotoDeleteView.as_view()),
]
