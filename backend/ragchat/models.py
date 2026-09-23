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


class UsageRecord(models.Model):
    """One billed action (question or upload), used to enforce usage limits."""

    QUESTION = "question"
    UPLOAD = "upload"

    client_id = models.CharField(max_length=64, db_index=True)
    kind = models.CharField(max_length=16, choices=[(QUESTION, "Question"), (UPLOAD, "Upload")])
    cost_usd = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
