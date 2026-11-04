from rest_framework import mixins, status, viewsets
from rest_framework.response import Response

from .models import Broker, RemovalRequest
from .serializers import BrokerSerializer, CreateRemovalRequestsSerializer, RemovalRequestSerializer
from .services import PlanLimitExceeded, brokers_for, create_requests


class BrokerViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = Broker.objects.filter(active=True)
    serializer_class = BrokerSerializer


class RemovalRequestViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet
):
    serializer_class = RemovalRequestSerializer

    def get_queryset(self):
        # Always scoped to the caller: users can never see each other's requests.
        qs = RemovalRequest.objects.filter(user=self.request.user).select_related("broker")
        wanted = self.request.query_params.get("status")
        if wanted in RemovalRequest.Status.values:
            qs = qs.filter(status=wanted)
        return qs

    def create(self, request, *args, **kwargs):
        payload = CreateRemovalRequestsSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        brokers = brokers_for(payload.validated_data.get("broker_ids"), payload.validated_data["all_brokers"])
        if not brokers:
            return Response({"detail": "No matching active brokers."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            created = create_requests(request.user, brokers)
        except PlanLimitExceeded as exc:
            return Response(
                {"detail": str(exc), "limit": exc.limit, "upgrade": "/api/billing/checkout/"},
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )
        data = RemovalRequestSerializer(created, many=True).data
        return Response({"created": len(created), "requests": data}, status=status.HTTP_201_CREATED)
