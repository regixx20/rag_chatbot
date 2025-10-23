"""Database models for the RAG chatbot API."""
from __future__ import annotations

from django.db import models


class Document(models.Model):
    """A document uploaded to enrich the RAG knowledge base."""

    file = models.FileField(upload_to="uploads/%Y/%m/%d")
    original_name = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self) -> str:
        return self.original_name
