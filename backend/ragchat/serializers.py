"""Serializers for API requests and responses."""
from __future__ import annotations

from rest_framework import serializers

from .models import Document


class DocumentSerializer(serializers.ModelSerializer):
    is_demo = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = ["id", "original_name", "file", "uploaded_at", "is_demo"]
        read_only_fields = ["id", "uploaded_at", "original_name", "is_demo"]
        extra_kwargs = {"file": {"write_only": True}}

    def get_is_demo(self, obj: Document) -> bool:
        return False


class ChatMessageSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=["user", "assistant"])
    content = serializers.CharField(allow_blank=True)


class ChatRequestSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=2000)
    mode = serializers.ChoiceField(choices=["rag", "direct"])
    history = ChatMessageSerializer(many=True, required=False, default=list)
