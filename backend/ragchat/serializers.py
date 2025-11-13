"""Serializers for API responses."""
from __future__ import annotations

from rest_framework import serializers

from .models import Document


class DocumentSerializer(serializers.ModelSerializer):
    class Meta: # manage upload of file and represent data for api
        model = Document
        fields = ["id", "original_name", "file", "uploaded_at"]
        read_only_fields = ["id", "uploaded_at"]


class ChatRequestSerializer(serializers.Serializer): # input format messages for validation of messages sent by users
    message = serializers.CharField()


class ChatResponseSerializer(serializers.Serializer):  # output format for chat responses
    response = serializers.CharField()
    intent = serializers.CharField()
    used_documents = serializers.ListField(
        child=serializers.CharField(), allow_empty=True
    )
