from django.contrib import admin
from .models import Transaction

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("date", "merchant", "amount", "currency", "in_out", "user")
    list_filter  = ("in_out", "currency", "user")
    search_fields = ("merchant", "notes")
