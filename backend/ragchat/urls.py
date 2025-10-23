"""Application level URL configuration."""
from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ChatView, DocumentViewSet

router = DefaultRouter()
router.register("documents", DocumentViewSet, basename="document")

urlpatterns = [
    path("chat/", ChatView.as_view(), name="chat"),
    path("", include(router.urls)),
]
