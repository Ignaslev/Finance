from django.contrib import admin
from .models import Transaction, Category, MoneySource, BalanceSnapshot, SavingsGoal, FeedbackTicket
from django.core.exceptions import PermissionDenied

@admin.register(FeedbackTicket)
class FeedbackTicketAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "user", "kind", "page", "status")
    list_filter = ("kind", "page", "status", "created_at")
    search_fields = ("user__email", "message")
    ordering = ("-created_at",)