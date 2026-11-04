from rest_framework import serializers

from .models import Broker, RemovalRequest


class BrokerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Broker
        fields = ("id", "name", "opt_out_url")


class RemovalRequestSerializer(serializers.ModelSerializer):
    broker = BrokerSerializer(read_only=True)

    class Meta:
        model = RemovalRequest
        fields = ("id", "broker", "status", "attempts", "last_error", "created_at", "updated_at", "submitted_at")
        read_only_fields = fields


class CreateRemovalRequestsSerializer(serializers.Serializer):
    broker_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False, max_length=200)
    all_brokers = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        has_ids = bool(attrs.get("broker_ids"))
        if has_ids == bool(attrs.get("all_brokers")):
            raise serializers.ValidationError("Send either 'broker_ids' or 'all_brokers': true.")
        return attrs
