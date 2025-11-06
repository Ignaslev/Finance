from django.conf import settings
from django.db import models

# ----- Existing choices -----
CATEGORY_CHOICES = [
    ("Cash", "Cash"),
    ("Dining", "Dining"),
    ("Fitness & Health", "Fitness & Health"),
    ("Groceries", "Groceries"),
    ("Shopping", "Shopping"),
    ("Crypto", "Crypto"),
    ("Utilities", "Utilities"),
    ("Other", "Other"),
]
SOURCE_CHOICES = [
    ("unknown", "Unknown"),
    ("user", "User"),
    ("ai", "AI"),
    ("rule", "Rule"),
    ("import", "Import"),
]


class Category(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=40)
    color = models.CharField(max_length=7, blank=True, default="")  # optional hex color
    monthly_cap = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        unique_together = ("user", "name")
        ordering = ["name"]

    def __str__(self):
        return self.name


class MoneySource(models.Model):
    TYPE_CHOICES = [
        ("bank", "Bank account"),
        ("cash", "Cash reserve"),
        ("savings", "Savings account"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="money_sources")
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default="bank")
    is_active = models.BooleanField(default=True)
    manual_balance = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    manual_currency = models.CharField(max_length=8, default="EUR")
    current_balance = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    balance_updated_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("user", "name")]
        indexes = [
            models.Index(fields=["user", "is_active"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_type_display()})"


class Transaction(models.Model):
    IN = "in"
    OUT = "out"
    IO_CHOICES = [(IN, "Income"), (OUT, "Spending")]

    # ---- AI fields ----
    ai_suggested_fk = models.ForeignKey(
        Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="ai_suggested_for"
    )
    ai_confidence = models.FloatField(null=True, blank=True)
    ai_reason = models.TextField(blank=True, default="")

    # ---- Categorization ----
    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES, null=True, blank=True)
    category_source = models.CharField(max_length=16, choices=SOURCE_CHOICES, default="unknown")
    user_note = models.TextField(blank=True, default="")
    category_fk = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL)
    updated_at = models.DateTimeField(auto_now=True)

    # ---- Ownership / linkage ----
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    money_source = models.ForeignKey(MoneySource, null=True, blank=True, on_delete=models.SET_NULL, related_name="transactions")

    # ---- Core fields ----
    date = models.DateField()
    merchant = models.CharField(max_length=255, blank=True, default="")
    amount = models.DecimalField(max_digits=12, decimal_places=2)  # positive; direction via in_out
    currency = models.CharField(max_length=8, default="EUR")
    in_out = models.CharField(max_length=3, choices=IO_CHOICES, default=OUT)
    notes = models.TextField(blank=True, default="")
    goal_fk = models.ForeignKey(
        "finance.SavingsGoal",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="transactions",
    )

    # per-user dedupe key (we will include source id when importing)
    fingerprint = models.CharField(max_length=64, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)

    # ---- Soft delete ----
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_note = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        unique_together = ("user", "fingerprint")
        ordering = ["-date", "-id"]
        indexes = [
            models.Index(fields=["user", "is_deleted", "date"]),
            models.Index(fields=["user", "is_deleted", "money_source", "date"]),
        ]

    def __str__(self):
        return f"{self.date} {self.merchant} {self.amount} {self.currency} {self.in_out}"


class BalanceSnapshot(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=8, default="EUR")
    timestamp = models.DateTimeField()  # when this balance was true
    note = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["user", "timestamp"]),
        ]

    def __str__(self):
        return f"{self.user} @ {self.timestamp:%Y-%m-%d %H:%M} = {self.amount} {self.currency}"

# --- SavingsGoal (MVP) ---
class SavingsGoal(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="savings_goals")
    name = models.CharField(max_length=100)
    target_amount = models.DecimalField(max_digits=12, decimal_places=2)
    is_active = models.BooleanField(default=True)
    accounts = models.ManyToManyField("MoneySource", related_name="goals", blank=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_active", "name"]

    def __str__(self):
        return f"{self.name} ({self.user})"
