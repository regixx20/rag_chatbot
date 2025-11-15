"""API endpoints for the RAG chatbot."""
from __future__ import annotations

import logging
from pathlib import Path

from django.conf import settings
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .chatbot import get_engine
from .models import Document
from .serializers import (
    ChatRequestSerializer,
    ChatResponseSerializer,
    DocumentSerializer,
)


logger = logging.getLogger(__name__)


class DocumentViewSet(viewsets.ModelViewSet):
    queryset = Document.objects.all()  # define which objects ModelViewSet works with
    serializer_class = DocumentSerializer # automatic by ModelViewSet to validate and format data
    parser_classes = [MultiPartParser] # parser to tranform request body into request data

    def perform_create(self, serializer: DocumentSerializer) -> None:  # type: ignore[override]
        uploaded_file = serializer.validated_data["file"]
        logger.info(
            "Téléversement reçu : nom=%s, taille=%s octets", uploaded_file.name, uploaded_file.size
        )
        document: Document = serializer.save(original_name=uploaded_file.name)
        engine = get_engine()
        ingested_sources = engine.ingest_files([Path(document.file.path)])
        logger.info(
            "Ingestion terminée pour %s. Sources ingérées : %s",
            uploaded_file.name,
            ingested_sources,
        )

    def perform_destroy(self, instance: Document) -> None:  # type: ignore[override]
        file_path = Path(instance.file.path) if instance.file else None
        document_name = instance.original_name
        logger.info("Suppression du document %s demandée", document_name)

        if instance.file:
            instance.file.delete(save=False)
        instance.delete()

        remaining_paths = [
            Path(doc.file.path)
            for doc in Document.objects.all()
            if doc.file and doc.file.name
        ]

        engine = get_engine()
        engine.rebuild_index(remaining_paths)

        if file_path and file_path.exists():
            try:
                file_path.unlink()
            except FileNotFoundError:
                pass

        logger.info(
            "Document %s supprimé. Index RAG reconstruit à partir des %s fichiers restants",
            document_name,
            len(remaining_paths),
        )

    @action(detail=False, methods=["post"], url_path="ingest")
    def ingest_existing(self, request, *args, **kwargs):
        engine = get_engine()
        docs_dir = Path(settings.BASE_DIR) / "docs"
        if not docs_dir.exists():
            logger.warning(
                "Demande d'ingestion de documents existants mais le dossier %s est introuvable",
                docs_dir,
            )
            return Response({"ingested_sources": []})
        file_paths = [path for path in docs_dir.glob("**/*") if path.is_file()]
        logger.info(
            "Ingestion manuelle déclenchée pour %s fichiers existants", len(file_paths)
        )
        ingested = engine.ingest_files(file_paths)
        logger.info("Ingestion existante terminée. Sources ingérées : %s", ingested)
        return Response({"ingested_sources": ingested})


class ChatView(APIView):
    def post(self, request, *args, **kwargs):
        serializer = ChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        engine = get_engine()
        message = serializer.validated_data["message"]
        mode = serializer.validated_data["mode"]
        history = serializer.validated_data.get("history", [])
        logger.info(
            "Requête de chat reçue : %s (mode=%s, historique=%s entrées)",
            message,
            mode,
            len(history),
        )
        answer, intent, sources = engine.chat(message, mode=mode, history=history)
        response_serializer = ChatResponseSerializer(
            {"response": answer, "intent": intent, "used_documents": sources}
        )
        logger.info(
            "Réponse envoyée au client. Intention=%s, documents=%s", intent, sources
        )
        return Response(response_serializer.data, status=status.HTTP_200_OK)
