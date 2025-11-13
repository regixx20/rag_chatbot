"""API endpoints for the RAG chatbot."""
from __future__ import annotations

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


class DocumentViewSet(viewsets.ModelViewSet):
    queryset = Document.objects.all()  # define which objects ModelViewSet works with
    serializer_class = DocumentSerializer # automatic by ModelViewSet to validate and format data
    parser_classes = [MultiPartParser] # parser to tranform request body into request data

    def perform_create(self, serializer: DocumentSerializer) -> None:  # type: ignore[override]
        uploaded_file = serializer.validated_data["file"]
        document: Document = serializer.save(original_name=uploaded_file.name)
        engine = get_engine()
        engine.ingest_files([Path(document.file.path)])

    @action(detail=False, methods=["post"], url_path="ingest")
    def ingest_existing(self, request, *args, **kwargs):
        engine = get_engine()
        docs_dir = Path(settings.BASE_DIR) / "docs"
        if not docs_dir.exists():
            return Response({"ingested_sources": []})
        file_paths = [path for path in docs_dir.glob("**/*") if path.is_file()]
        ingested = engine.ingest_files(file_paths)
        return Response({"ingested_sources": ingested})


class ChatView(APIView):
    def post(self, request, *args, **kwargs):
        serializer = ChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        engine = get_engine()
        answer, intent, sources = engine.chat(serializer.validated_data["message"])
        response_serializer = ChatResponseSerializer(
            {"response": answer, "intent": intent, "used_documents": sources}
        )
        return Response(response_serializer.data, status=status.HTTP_200_OK)
