from rest_framework.routers import DefaultRouter

from .views import BrokerViewSet, RemovalRequestViewSet

router = DefaultRouter()
router.register("brokers", BrokerViewSet, basename="broker")
router.register("requests", RemovalRequestViewSet, basename="removal-request")
urlpatterns = router.urls
