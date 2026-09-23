"""Database models for the RAG chatbot API."""
from __future__ import annotations

from django.db import models


class Document(models.Model):
    """A document uploaded by a visitor. Each visitor session only sees its own documents."""

    session_id = models.CharField(max_length=64, db_index=True, default="")
    file = models.FileField(upload_to="uploads/%Y/%m/%d")
    original_name = models.CharField(max_length=255)
    chunk_count = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self) -> str:
        return self.original_name
