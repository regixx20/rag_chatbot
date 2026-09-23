from django.contrib import admin

from .models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("original_name", "session_id", "chunk_count", "uploaded_at")
    search_fields = ("original_name", "session_id")
    ordering = ("-uploaded_at",)
