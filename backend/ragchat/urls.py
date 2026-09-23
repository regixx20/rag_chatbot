"""Application level URL configuration."""
from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ChatStreamView, ChatView, DocumentViewSet, HealthView

router = DefaultRouter()
router.register("documents", DocumentViewSet, basename="document")

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("chat/", ChatView.as_view(), name="chat"),
    path("chat/stream/", ChatStreamView.as_view(), name="chat-stream"),
    path("", include(router.urls)),
]
