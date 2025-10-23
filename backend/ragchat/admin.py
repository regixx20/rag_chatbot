from django.contrib import admin

from .models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("original_name", "uploaded_at")
    search_fields = ("original_name",)
    ordering = ("-uploaded_at",)
