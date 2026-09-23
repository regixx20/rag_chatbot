"""Usage limits protecting the API keys of the public demo.

Three independent guards, all configurable through environment variables:
- per visitor (hashed IP): questions per hour and per day;
- global: a daily number of questions for the whole site, kept under the
  Gemini free-tier quotas;
- uploads: documents per session and per visitor per day.

The Gemini free tier never bills: past its quotas the API refuses requests
instead, so these limits keep the demo usable for everyone.
"""
from __future__ import annotations

import hashlib
import os
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import Document, UsageRecord

MAX_QUESTIONS_PER_HOUR = int(os.getenv("RAG_MAX_QUESTIONS_PER_HOUR", "20"))
MAX_QUESTIONS_PER_DAY = int(os.getenv("RAG_MAX_QUESTIONS_PER_DAY", "60"))
MAX_QUESTIONS_GLOBAL_PER_DAY = int(os.getenv("RAG_MAX_QUESTIONS_GLOBAL_PER_DAY", "300"))
MAX_DOCUMENTS_PER_SESSION = int(os.getenv("RAG_MAX_DOCUMENTS_PER_SESSION", "5"))
MAX_UPLOADS_PER_DAY = int(os.getenv("RAG_MAX_UPLOADS_PER_DAY", "15"))


class LimitExceeded(Exception):
    """Raised with a user-facing message when a quota is reached."""


def client_id(request) -> str:
    """Stable, non-reversible id for the visitor (Render sits behind a proxy)."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = forwarded.split(",")[0].strip() or request.META.get("REMOTE_ADDR", "unknown")
    return hashlib.sha256(f"{settings.SECRET_KEY}:{ip}".encode()).hexdigest()[:32]


def _start_of_day():
    return timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)


def global_quota_reached() -> bool:
    questions_today = UsageRecord.objects.filter(
        kind=UsageRecord.QUESTION, created_at__gte=_start_of_day()
    ).count()
    return questions_today >= MAX_QUESTIONS_GLOBAL_PER_DAY


def check_question(request) -> None:
    visitor = client_id(request)
    now = timezone.now()
    questions = UsageRecord.objects.filter(client_id=visitor, kind=UsageRecord.QUESTION)

    if global_quota_reached():
        raise LimitExceeded(
            "La démo a atteint sa limite d'utilisation pour aujourd'hui. Revenez demain !"
        )
    if questions.filter(created_at__gte=now - timedelta(hours=1)).count() >= MAX_QUESTIONS_PER_HOUR:
        raise LimitExceeded(
            f"Vous avez atteint la limite de {MAX_QUESTIONS_PER_HOUR} questions par heure. "
            "Réessayez un peu plus tard."
        )
    if questions.filter(created_at__gte=now - timedelta(days=1)).count() >= MAX_QUESTIONS_PER_DAY:
        raise LimitExceeded(
            f"Vous avez atteint la limite de {MAX_QUESTIONS_PER_DAY} questions par jour. Revenez demain !"
        )


def check_upload(request, session_id: str) -> None:
    visitor = client_id(request)
    if Document.objects.filter(session_id=session_id).count() >= MAX_DOCUMENTS_PER_SESSION:
        raise LimitExceeded(
            f"Vous pouvez ajouter au maximum {MAX_DOCUMENTS_PER_SESSION} documents. "
            "Supprimez-en un pour en ajouter un autre."
        )
    uploads_today = UsageRecord.objects.filter(
        client_id=visitor, kind=UsageRecord.UPLOAD, created_at__gte=timezone.now() - timedelta(days=1)
    ).count()
    if uploads_today >= MAX_UPLOADS_PER_DAY:
        raise LimitExceeded("Limite d'ajout de documents atteinte pour aujourd'hui. Revenez demain !")
    if global_quota_reached():
        raise LimitExceeded("La démo a atteint sa limite d'utilisation pour aujourd'hui. Revenez demain !")


def record(request, kind: str, cost_usd: float = 0.0) -> None:
    UsageRecord.objects.create(client_id=client_id(request), kind=kind, cost_usd=cost_usd)
    # Keep the table small: nothing older than two days is ever read
    UsageRecord.objects.filter(created_at__lt=timezone.now() - timedelta(days=2)).delete()
