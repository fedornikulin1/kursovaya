from rest_framework.routers import DefaultRouter
from .api import TicketViewSet

router = DefaultRouter()
router.register("tickets", TicketViewSet, basename="support-ticket")
urlpatterns = router.urls
