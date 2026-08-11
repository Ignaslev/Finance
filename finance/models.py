from django.conf import settings
from django.db import models
from django.utils.crypto import get_random_string
from django.utils import timezone
from datetime import timedelta
from django.utils.translation import gettext_lazy as _

# ----- Existing choices -----
# ----- Category choices come from settings -----
CATEGORY_CHOICES = [(c, c) for c in getattr(settings, "DEFAULT_CATEGORIES", [])]

SOURCE_CHOICES = [
    ("unknown", _("Unknown")),
    ("user", _("User")),
    ("ai", _("AI")),
    ("rule", _("Rule")),
    ("import", _("Import")),
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
        ("bank", _("Bank account")),
        ("cash", _("Cash reserve")),
        ("savings", _("Savings account")),
        ("investment", _("Investment")),
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
    IO_CHOICES = [(IN, _("Income")), (OUT, _("Spending"))]

    import_batch = models.ForeignKey(
        "ImportBatch",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transactions",
    )

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
    intro_acknowledged_at = models.DateTimeField(null=True, blank=True)
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


# --- UNIFIED ASSET TRACKING ---

class Asset(models.Model):
    TYPE_CHOICES = [
        ('crypto', 'Crypto'),
        ('stock', 'Stock/ETF'),
    ]

    # identification
    symbol = models.CharField(max_length=20)  # e.g. 'BTC', 'AAPL', 'VWCE'
    lookup_key = models.CharField(max_length=100, unique=True)
    # ^ For Crypto: CoinGecko ID (e.g. 'bitcoin')
    # ^ For Stocks: Yahoo Ticker (e.g. 'AAPL', 'VWCE.DE')

    name = models.CharField(max_length=100)
    asset_type = models.CharField(max_length=10, choices=TYPE_CHOICES)

    # We normalize EVERYTHING to EUR for simple math in the app
    current_price_eur = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    price_updated_at = models.DateTimeField(null=True, blank=True)

    # Metadata
    currency_raw = models.CharField(max_length=5, default="EUR")  # Original currency (USD, EUR)

    def __str__(self):
        return f"{self.symbol} ({self.asset_type})"


class AssetHolding(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='assets')
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)

    # The "Virtual" Account this belongs to (e.g., "Trading 212" or "Ledger Nano")
    money_source = models.ForeignKey(
        MoneySource,
        on_delete=models.SET_NULL,  # Changed to SET_NULL
        null=True,
        blank=True,
        related_name='holdings'
    )

    quantity = models.DecimalField(max_digits=20, decimal_places=8)

    class Meta:
        unique_together = ('user', 'asset',
                           'money_source')  # You might want to remove 'money_source' from unique if it's auto-assigned, but keeping it is fine for now.

    @property
    def value_eur(self):
        # Safety check if price is missing
        return self.quantity * (self.asset.current_price_eur or 0)


class PortfolioSnapshot(models.Model):
    """
    Daily history of portfolio value for graphing.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='portfolio_history')
    timestamp = models.DateTimeField(auto_now_add=True)

    crypto_total = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    stock_total = models.DecimalField(max_digits=20, decimal_places=2, default=0)

    class Meta:
        ordering = ['timestamp']
        indexes = [
            models.Index(fields=['user', 'timestamp']),
        ]

    @property
    def total(self):
        return self.crypto_total + self.stock_total



from django.utils.crypto import get_random_string

class UserProfile(models.Model):
    """
    Stores app-specific user settings (e.g. API keys and display preferences).
    """
    SUBSCRIPTION_TRIAL = "trial"
    SUBSCRIPTION_BETA = "beta"
    SUBSCRIPTION_ACTIVE = "active"
    SUBSCRIPTION_TRIALING = "trialing"
    SUBSCRIPTION_PAST_DUE = "past_due"
    SUBSCRIPTION_CANCELED = "canceled"
    SUBSCRIPTION_EXPIRED = "expired"
    SUBSCRIPTION_MANUAL = "manual"

    SUBSCRIPTION_STATUS_CHOICES = [
        (SUBSCRIPTION_TRIAL, _("Trial")),
        (SUBSCRIPTION_BETA, _("Beta access")),
        (SUBSCRIPTION_ACTIVE, _("Active")),
        (SUBSCRIPTION_TRIALING, _("Trialing")),
        (SUBSCRIPTION_PAST_DUE, _("Past due")),
        (SUBSCRIPTION_CANCELED, _("Canceled")),
        (SUBSCRIPTION_EXPIRED, _("Expired")),
        (SUBSCRIPTION_MANUAL, _("Manual access")),
    ]

    PLAN_MONTHLY = "monthly"
    PLAN_YEARLY = "yearly"
    PLAN_CHOICES = [
        (PLAN_MONTHLY, _("Monthly")),
        (PLAN_YEARLY, _("Yearly")),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    android_webhook_secret = models.CharField(max_length=64, unique=True, blank=True)

    is_beta_tester = models.BooleanField(default=False)
    beta_joined_at = models.DateTimeField(null=True, blank=True)
    beta_access_until = models.DateTimeField(null=True, blank=True)

    acquisition_source = models.CharField(max_length=100, blank=True, default="", db_index=True)
    acquisition_medium = models.CharField(max_length=100, blank=True, default="")
    acquisition_campaign = models.CharField(max_length=100, blank=True, default="", db_index=True)
    acquisition_content = models.CharField(max_length=100, blank=True, default="")
    acquisition_term = models.CharField(max_length=100, blank=True, default="")
    acquisition_landing_page = models.CharField(max_length=255, blank=True, default="")
    acquisition_referrer = models.CharField(max_length=255, blank=True, default="")

    subscription_status = models.CharField(
        max_length=20,
        choices=SUBSCRIPTION_STATUS_CHOICES,
        default=SUBSCRIPTION_TRIAL,
        db_index=True,
    )
    plan_interval = models.CharField(max_length=10, choices=PLAN_CHOICES, blank=True, default="")
    trial_started_at = models.DateTimeField(null=True, blank=True)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    manual_access_until = models.DateTimeField(null=True, blank=True)
    manual_access_note = models.CharField(max_length=255, blank=True, default="")

    stripe_customer_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    stripe_subscription_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    stripe_price_id = models.CharField(max_length=255, blank=True, default="")
    stripe_current_period_end = models.DateTimeField(null=True, blank=True)
    stripe_cancel_at_period_end = models.BooleanField(default=False)
    stripe_last_event_id = models.CharField(max_length=255, blank=True, default="")
    stripe_owner_notified_subscription_id = models.CharField(max_length=255, blank=True, default="")
    subscription_updated_at = models.DateTimeField(null=True, blank=True)

    account_delete_requested_at = models.DateTimeField(null=True, blank=True)
    account_delete_scheduled_for = models.DateTimeField(null=True, blank=True)
    account_delete_canceled_at = models.DateTimeField(null=True, blank=True)

    # If True: show investment values after subtracting 15% (flat estimate)
    exclude_investment_tax = models.BooleanField(default=False)

    LANG_LT = "lt"
    LANG_EN = "en"



    LANGUAGE_CHOICES = [
        (LANG_LT, _("Lithuanian")),
        (LANG_EN, _("English")),
    ]

    preferred_language = models.CharField(
        max_length=2,
        choices=LANGUAGE_CHOICES,
        default=LANG_LT,
    )

    default_import_source = models.ForeignKey(
        "finance.MoneySource",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    @property
    def access_until(self):
        dates = [
            self.beta_access_until if self.is_beta_tester else None,
            self.trial_ends_at,
            self.manual_access_until,
        ]

        if self.subscription_status in {self.SUBSCRIPTION_ACTIVE, self.SUBSCRIPTION_TRIALING}:
            dates.append(self.stripe_current_period_end)

        valid_dates = [value for value in dates if value]
        return max(valid_dates) if valid_dates else None

    def has_active_access(self, now=None):
        now = now or timezone.now()

        if self.user_id and (self.user.is_staff or self.user.is_superuser):
            return True

        if self.manual_access_until and self.manual_access_until > now:
            return True

        if self.is_beta_tester and self.beta_access_until and self.beta_access_until > now:
            return True

        if self.subscription_status == self.SUBSCRIPTION_TRIAL and self.trial_ends_at and self.trial_ends_at > now:
            return True

        if self.subscription_status in {self.SUBSCRIPTION_ACTIVE, self.SUBSCRIPTION_TRIALING}:
            return self.stripe_current_period_end is None or self.stripe_current_period_end > now

        return False

    @property
    def access_source(self):
        now = timezone.now()
        if self.user_id and (self.user.is_staff or self.user.is_superuser):
            return "admin"
        if self.manual_access_until and self.manual_access_until > now:
            return "manual"
        if self.is_beta_tester and self.beta_access_until and self.beta_access_until > now:
            return "beta"
        if self.subscription_status == self.SUBSCRIPTION_TRIAL and self.trial_ends_at and self.trial_ends_at > now:
            return "trial"
        if self.subscription_status in {self.SUBSCRIPTION_ACTIVE, self.SUBSCRIPTION_TRIALING} and self.has_active_access(now):
            return "stripe"
        return "expired"

    def save(self, *args, **kwargs):
        if not self.android_webhook_secret:
            self.android_webhook_secret = get_random_string(length=32)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Profile for {self.user}"


class ImportBatch(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="import_batches",
    )
    money_source = models.ForeignKey(
        "MoneySource",
        on_delete=models.CASCADE,
        related_name="import_batches",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    filename = models.CharField(max_length=255, blank=True)
    bank_key = models.CharField(max_length=32, blank=True)  # auto/revolut/seb/swedbank

    added_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    dup_count = models.PositiveIntegerField(default=0)

    undone_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user_id} {self.bank_key} {self.created_at:%Y-%m-%d %H:%M}"

class PendingDataDeletion(models.Model):
    SCOPE_TRANSACTIONS = "transactions"
    SCOPE_CHOICES = [
        (SCOPE_TRANSACTIONS, "Transactions"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pending_data_deletions",
    )
    scope = models.CharField(
        max_length=32,
        choices=SCOPE_CHOICES,
        default=SCOPE_TRANSACTIONS,
    )
    requested_at = models.DateTimeField(null=True, blank=True)
    scheduled_for = models.DateTimeField(null=True, blank=True, db_index=True)
    canceled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "scope"],
                name="uniq_pending_data_deletion_user_scope",
            )
        ]
        indexes = [
            models.Index(fields=["scope", "scheduled_for"]),
        ]

    def __str__(self):
        return f"{self.user_id} {self.scope} {self.scheduled_for or '-'}"


class SubscriptionDecision(models.Model):
    DECISION_TRACK = "track"
    DECISION_IGNORE = "ignore"
    DECISION_UNTRACK = "untrack"
    DECISION_ENDED = "ended"
    DECISION_CHOICES = [
        (DECISION_TRACK, "Track"),
        (DECISION_IGNORE, "Ignore"),
        (DECISION_UNTRACK, "Untrack"),
        (DECISION_ENDED, "Ended"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscription_decisions",
    )
    normalized_merchant = models.CharField(max_length=255)
    display_name = models.CharField(max_length=255, blank=True, default="")
    decision = models.CharField(max_length=16, choices=DECISION_CHOICES)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "normalized_merchant"],
                name="uniq_subscription_decision_user_merchant",
            )
        ]
        indexes = [
            models.Index(fields=["user", "decision"]),
            models.Index(fields=["user", "normalized_merchant"]),
        ]
        ordering = ["normalized_merchant"]

    def __str__(self):
        return f"{self.user_id} {self.normalized_merchant} {self.decision}"

class IncomeSourceDecision(models.Model):
    DECISION_TRACK = "track"
    DECISION_IGNORE = "ignore"
    DECISION_UNTRACK = "untrack"
    DECISION_CHOICES = [
        (DECISION_TRACK, "Track"),
        (DECISION_IGNORE, "Ignore"),
        (DECISION_UNTRACK, "Untrack"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="income_source_decisions",
    )
    normalized_merchant = models.CharField(max_length=255)
    display_name = models.CharField(max_length=255, blank=True, default="")
    decision = models.CharField(max_length=16, choices=DECISION_CHOICES)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "normalized_merchant"],
                name="uniq_income_source_decision_user_merchant",
            )
        ]
        indexes = [
            models.Index(fields=["user", "decision"]),
            models.Index(fields=["user", "normalized_merchant"]),
        ]
        ordering = ["normalized_merchant"]

    def __str__(self):
        return f"{self.user_id} {self.normalized_merchant} {self.decision}"


class RefundPairIgnore(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ignored_refund_pairs",
    )
    tx_out = models.ForeignKey(
        "Transaction",
        on_delete=models.CASCADE,
        related_name="refund_ignored_as_out",
    )
    tx_in = models.ForeignKey(
        "Transaction",
        on_delete=models.CASCADE,
        related_name="refund_ignored_as_in",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "tx_out", "tx_in"],
                name="uniq_refund_ignore_user_pair",
            )
        ]
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["user", "created_at"]),
        ]

    def __str__(self):
        return f"{self.user_id} refund-ignore {self.tx_out_id}->{self.tx_in_id}"


from django.conf import settings
from django.db import models

class FeedbackTicket(models.Model):
    KIND_BUG = "bug"
    KIND_IDEA = "idea"
    KIND_CHOICES = [
        (KIND_BUG, _("Bug")),
        (KIND_IDEA, _("Idea")),
    ]

    STATUS_NEW = "new"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_DONE = "done"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_NEW, _("New")),
        (STATUS_IN_PROGRESS, _("In progress")),
        (STATUS_DONE, _("Done")),
        (STATUS_REJECTED, _("Rejected")),
    ]

    PAGE_OVERVIEW = "overview"
    PAGE_TRANSACTIONS = "transactions"
    PAGE_IMPORT = "import"
    PAGE_ASSETS = "assets"
    PAGE_PROFILE = "profile"
    PAGE_AI = "ai"
    PAGE_OTHER = "other"
    PAGE_CHOICES = [
        (PAGE_OVERVIEW, _("Overview")),
        (PAGE_TRANSACTIONS, _("Transactions")),
        (PAGE_IMPORT, _("Import")),
        (PAGE_ASSETS, _("Assets")),
        (PAGE_PROFILE, _("Profile")),
        (PAGE_AI, _("AI")),
        (PAGE_OTHER, _("Other")),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="feedback_tickets")
    kind = models.CharField(max_length=8, choices=KIND_CHOICES)
    page = models.CharField(max_length=20, choices=PAGE_CHOICES, default=PAGE_OTHER)
    message = models.TextField()

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user_id} {self.kind} {self.page} {self.status} {self.created_at:%Y-%m-%d}"
