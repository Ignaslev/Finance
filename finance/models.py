from django.conf import settings
from django.db import models

# ----- Existing choices -----
# ----- Category choices come from settings -----
CATEGORY_CHOICES = [(c, c) for c in getattr(settings, "DEFAULT_CATEGORIES", [])]

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

# finance/models.py (add at the bottom)
from django.conf import settings
from django.db import models

class AdvisorReport(models.Model):
    TYPE_MONTHLY = "monthly"
    TYPE_WEEKLY = "weekly"
    TYPE_CHOICES = (
        (TYPE_MONTHLY, "Monthly"),
        (TYPE_WEEKLY, "Weekly"),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    type = models.CharField(max_length=16, choices=TYPE_CHOICES)
    period_start = models.DateField()
    period_end = models.DateField()

    # What we sent & what we got back (compact JSON)
    payload = models.JSONField(null=True, blank=True)
    response = models.JSONField(null=True, blank=True)

    previous = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL)
    model = models.CharField(max_length=64, default="gpt-4o-mini")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "type", "period_start", "period_end")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} {self.type} {self.period_start}..{self.period_end}"

class BalanceAnomaly(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    detected_at = models.DateTimeField(auto_now_add=True)

    # snapshots that bracket the anomaly
    snapshot_prev = models.ForeignKey('BalanceSnapshot', on_delete=models.CASCADE, related_name='anomaly_next', null=True, blank=True)
    snapshot_curr = models.ForeignKey('BalanceSnapshot', on_delete=models.CASCADE, related_name='anomaly_prev', null=True, blank=True)

    # numbers (store as Decimal)
    prev_amount = models.DecimalField(max_digits=14, decimal_places=2)   # what you entered before
    curr_amount = models.DecimalField(max_digits=14, decimal_places=2)   # what you entered now
    tx_delta_between = models.DecimalField(max_digits=14, decimal_places=2)  # Σ(in)−Σ(out) between prev→curr
    expected_curr = models.DecimalField(max_digits=14, decimal_places=2)     # prev_amount + tx_delta_between
    diff = models.DecimalField(max_digits=14, decimal_places=2)              # curr_amount − expected_curr

    note = models.CharField(max_length=240, blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=['user','detected_at']),
        ]
        ordering = ['-detected_at']


class OnboardingState(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="onboarding_state")
    # Step completion flags
    categories_done = models.BooleanField(default=False)
    upload_done = models.BooleanField(default=False)
    balance_done = models.BooleanField(default=False)
    teach_ai_done = models.BooleanField(default=False)
    ready_dismissed = models.BooleanField(default=False)
    # Housekeeping
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def done_all(self):
        # If you want the banner to disappear forever after “ready_dismissed”:
        return self.ready_dismissed

    def __str__(self):
        return f"OnboardingState<{self.user_id}>"

# --- AI run logs ---------------------------------------------------------------
class AiRun(models.Model):
    KIND_CHOICES = [
        ("autocategorize", "Auto-categorize"),
        ("recheck", "Recheck"),
    ]
    STATUS_CHOICES = [
        ("queued", "Queued"),
        ("running", "Running"),
        ("done", "Done"),
        ("failed", "Failed"),
    ]
    MODE_CHOICES = [
        ("uncat", "Uncategorized only"),
        ("ai", "AI-labeled"),
        ("all", "All (excl. user)"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ai_runs")
    kind = models.CharField(max_length=32, choices=KIND_CHOICES)
    mode = models.CharField(max_length=16, choices=MODE_CHOICES, default="uncat")
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="queued")

    considered = models.PositiveIntegerField(default=0)
    applied = models.PositiveIntegerField(default=0)
    parked = models.PositiveIntegerField(default=0)
    skipped = models.PositiveIntegerField(default=0)

    log_text = models.TextField(blank=True, default="")

    # simple per-user run lock/cooldown helper fields
    locked_at = models.DateTimeField(null=True, blank=True)

    notified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "started_at"]),
            models.Index(fields=["user", "status"]),
            models.Index(fields=["kind", "status"]),
        ]

    def __str__(self):
        return f"AiRun<{self.user_id} {self.kind} {self.mode} {self.status} {self.started_at:%Y-%m-%d %H:%M:%S}>"


class AiRunItem(models.Model):
    ACTION_CHOICES = [
        ("applied", "Applied"),
        ("parked", "Parked"),
        ("skipped", "Skipped"),
    ]
    run = models.ForeignKey(AiRun, on_delete=models.CASCADE, related_name="items")
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="ai_run_items")

    old_category_fk = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    new_category_fk = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    confidence = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    reason = models.TextField(blank=True, default="")
    action = models.CharField(max_length=16, choices=ACTION_CHOICES)

    class Meta:
        indexes = [
            models.Index(fields=["run"]),
            models.Index(fields=["transaction"]),
        ]

    def __str__(self):
        return f"AiRunItem<{self.run_id} tx={self.transaction_id} {self.action}>"
