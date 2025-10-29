from django.contrib import admin
from .models import Transaction, Category, MoneySource, BalanceSnapshot

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("date", "merchant", "amount", "currency", "in_out", "user", "money_source", "category_fk", "category_source", "is_deleted")
    list_filter  = ("in_out", "currency", "user", "money_source", "category_source", "is_deleted")
    search_fields = ("merchant", "notes", "user_note", "fingerprint")
    date_hierarchy = "date"

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "color")
    list_filter = ("user",)
    search_fields = ("name",)

@admin.register(MoneySource)
class MoneySourceAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "type", "is_active", "current_balance", "balance_updated_at", "created_at")
    list_filter = ("type", "is_active", "user")
    search_fields = ("name",)

@admin.register(BalanceSnapshot)
class BalanceSnapshotAdmin(admin.ModelAdmin):
    list_display = ("user", "amount", "currency", "timestamp", "note", "created_at")
    list_filter = ("user", "currency")
    date_hierarchy = "timestamp"
