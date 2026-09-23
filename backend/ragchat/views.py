"""API endpoints for the RAG chatbot."""
from __future__ import annotations

import json
import logging
import re
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.http import StreamingHttpResponse
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from . import limits
from .chatbot import SUPPORTED_EXTENSIONS, StreamResult, get_engine
from .models import Document, UsageRecord
from .serializers import ChatRequestSerializer, DocumentSerializer

logger = logging.getLogger(__name__)

SESSION_HEADER = "HTTP_X_SESSION_ID"
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9-]{8,64}$")
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
SESSION_TTL = timedelta(hours=24)


def get_session_id(request) -> str:
    session_id = request.META.get(SESSION_HEADER, "")
    if not SESSION_ID_PATTERN.match(session_id):
        raise ValidationError({"detail": "En-tête X-Session-Id manquant ou invalide."})
    return session_id


def engine_or_error():
    """Return (engine, None) or (None, error response) when OpenAI isn't configured."""
    try:
        return get_engine(), None
    except RuntimeError:
        logger.exception("Moteur de chatbot indisponible")
        return None, Response(
            {"detail": "Le serveur n'est pas configuré (clé d'API manquante)."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


def limit_response(error: limits.LimitExceeded) -> Response:
    return Response({"detail": str(error)}, status=status.HTTP_429_TOO_MANY_REQUESTS)


def purge_expired_sessions() -> None:
    """Visitors' documents are temporary: drop sessions idle for more than SESSION_TTL."""
    expired = Document.objects.filter(uploaded_at__lt=timezone.now() - SESSION_TTL)
    session_ids = set(expired.values_list("session_id", flat=True))
    active = set(
        Document.objects.filter(session_id__in=session_ids, uploaded_at__gte=timezone.now() - SESSION_TTL)
        .values_list("session_id", flat=True)
    )
    for session_id in session_ids - active:
        for document in Document.objects.filter(session_id=session_id):
            document.file.delete(save=False)
            document.delete()
        try:
            get_engine().drop_session(session_id)
        except RuntimeError:
            pass
        logger.info("Session expirée supprimée : %s", session_id)


class HealthView(APIView):
    """Lightweight endpoint used by the frontend to wake the server up."""

    def get(self, request, *args, **kwargs):
        return Response({"status": "ok"})


class DocumentViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = DocumentSerializer
    parser_classes = [MultiPartParser]

    def get_queryset(self):
        return Document.objects.filter(session_id=get_session_id(self.request))

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        demo = []
        engine, _ = engine_or_error()
        if engine is not None:
            demo = [
                {"id": f"demo-{path.name}", "original_name": path.name, "uploaded_at": None, "is_demo": True}
                for path in engine.demo_files()
            ]
        return Response([*response.data, *demo])

    def create(self, request, *args, **kwargs):
        session_id = get_session_id(request)
        engine, error = engine_or_error()
        if error:
            return error

        uploaded = request.FILES.get("file")
        if uploaded is None:
            return Response({"detail": "Aucun fichier reçu."}, status=status.HTTP_400_BAD_REQUEST)
        if Path(uploaded.name).suffix.lower() not in SUPPORTED_EXTENSIONS:
            return Response(
                {"detail": "Format non pris en charge. Formats acceptés : PDF, DOCX, TXT, MD, HTML, XML, JSON, CSV."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if uploaded.size > MAX_UPLOAD_BYTES:
            return Response(
                {"detail": "Fichier trop volumineux (10 Mo maximum)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            limits.check_upload(request, session_id)
        except limits.LimitExceeded as exceeded:
            return limit_response(exceeded)

        purge_expired_sessions()
        limits.record(request, UsageRecord.UPLOAD)
        document = Document.objects.create(
            session_id=session_id, file=uploaded, original_name=uploaded.name
        )
        logger.info("Téléversement reçu : %s (%s octets)", uploaded.name, uploaded.size)

        try:
            chunk_count = engine.ingest(session_id, document.id, Path(document.file.path), uploaded.name)
        except Exception:
            logger.exception("Échec de l'indexation de %s", uploaded.name)
            chunk_count = 0

        if chunk_count == 0:
            document.file.delete(save=False)
            document.delete()
            return Response(
                {"detail": "Impossible d'extraire du texte de ce fichier (document scanné, vide ou protégé ?)."},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        document.chunk_count = chunk_count
        document.save(update_fields=["chunk_count"])
        return Response(self.get_serializer(document).data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance: Document) -> None:
        engine, _ = engine_or_error()
        if engine is not None:
            engine.remove(instance.session_id, instance.id, instance.chunk_count)
        instance.file.delete(save=False)
        instance.delete()
        logger.info("Document %s supprimé", instance.original_name)


class ChatView(APIView):
    """Non-streamed chat, kept for simple clients (and the CLI-like usage)."""

    def post(self, request, *args, **kwargs):
        session_id = get_session_id(request)
        serializer = ChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        engine, error = engine_or_error()
        if error:
            return error

        try:
            limits.check_question(request)
        except limits.LimitExceeded as exceeded:
            return limit_response(exceeded)

        data = serializer.validated_data
        result = StreamResult()
        try:
            prepared = engine.prepare(data["message"], data["mode"], data["history"], session_id)
            answer = engine.answer(prepared, result)
        except Exception:
            logger.exception("Échec de la génération de la réponse")
            return Response(
                {"detail": "Le modèle de langage n'a pas pu répondre. Réessayez dans un instant."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        limits.record(request, UsageRecord.QUESTION, result.cost_usd)
        sources = [source.as_dict() for source in prepared.sources]
        return Response(
            {
                "response": answer,
                "intent": prepared.intent,
                "sources": sources,
                "used_documents": sorted({source["document"] for source in sources}),
            }
        )


class ChatStreamView(APIView):
    """Streamed chat as NDJSON: one `meta` event (intent + sources), `token` events,
    then `done` — or an `error` event if the LLM fails midway."""

    def post(self, request, *args, **kwargs):
        session_id = get_session_id(request)
        serializer = ChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        engine, error = engine_or_error()
        if error:
            return error

        try:
            limits.check_question(request)
        except limits.LimitExceeded as exceeded:
            return limit_response(exceeded)

        data = serializer.validated_data
        result = StreamResult()
        try:
            prepared = engine.prepare(data["message"], data["mode"], data["history"], session_id)
        except Exception:
            logger.exception("Échec de la préparation de la réponse")
            return Response(
                {"detail": "La recherche dans les documents a échoué. Réessayez dans un instant."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        def events():
            def line(payload: dict) -> str:
                return json.dumps(payload, ensure_ascii=False) + "\n"

            yield line(
                {
                    "type": "meta",
                    "intent": prepared.intent,
                    "sources": [source.as_dict() for source in prepared.sources],
                }
            )
            try:
                for token in engine.stream(prepared, result):
                    yield line({"type": "token", "content": token})
            except Exception:
                logger.exception("Échec pendant le streaming de la réponse")
                yield line(
                    {"type": "error", "detail": "La génération de la réponse a été interrompue."}
                )
                return
            finally:
                # Count the question even when the stream fails midway (tokens were spent)
                limits.record(request, UsageRecord.QUESTION, result.cost_usd or prepared.cost_usd)
            yield line({"type": "done"})

        response = StreamingHttpResponse(events(), content_type="application/x-ndjson")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response
