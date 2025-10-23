"""Serializers for API responses."""
from __future__ import annotations

from rest_framework import serializers

from .models import Document


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ["id", "original_name", "file", "uploaded_at"]
        read_only_fields = ["id", "uploaded_at"]


class ChatRequestSerializer(serializers.Serializer):
    message = serializers.CharField()


class ChatResponseSerializer(serializers.Serializer):
    response = serializers.CharField()
    intent = serializers.CharField()
    used_documents = serializers.ListField(
        child=serializers.CharField(), allow_empty=True
    )
