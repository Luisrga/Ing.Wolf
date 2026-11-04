from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    class Meta:
        model = User
        fields = ("username", "email", "password")

    def validate(self, attrs):
        # Passing the unsaved user lets the similarity validator compare fields.
        candidate = User(username=attrs.get("username", ""), email=attrs.get("email", ""))
        validate_password(attrs["password"], candidate)
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)
