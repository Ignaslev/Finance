from django.urls import path
from django.contrib.auth import views as auth_views
from . import views as f
from .views import transactions
from .views import settings as settings_views

urlpatterns = [
    path("app/", f.upload, name="upload"),
    path("overview/", f.overview, name="overview"),
    path("upload/", f.upload),
    path("statistics/", f.statistics, name="statistics"),
    path("tx/bulk-apply/", f.tx_bulk_category_apply, name="tx_bulk_category_apply"),


    path("uncategorized/", f.uncategorized, name="uncategorized"),
    path("tx/<int:pk>/edit/", f.tx_edit, name="tx_edit"),
    path("tx/add/", f.tx_add, name="tx_add"),
    path("undo-last-import/", transactions.undo_last_import, name="undo_last_import"),
    path("data/delete-transactions/", transactions.data_delete_transactions, name="data_delete_transactions"),
    path("data/cancel-delete-transactions/", transactions.cancel_data_delete_transactions,
         name="cancel_data_delete_transactions"),

# NEW: auto-categorize endpoint (runs only when you click)
    path("ai/full/", f.ai_full_categorize, name="ai_full_categorize"),

# NEW review pages
    path("review/low/", f.review_low_conf, name="review_low_conf"),
    path("review/low/apply/", f.review_low_apply, name="review_low_apply"),
    path("review/subscriptions/", f.review_subscription_candidates, name="review_subscription_candidates"),
    path("review/subscriptions/apply/", f.review_subscription_candidates_apply,
         name="review_subscription_candidates_apply"),
    path("review/subscriptions/untracked/", f.untracked_subscriptions, name="untracked_subscriptions"),
    path("review/subscriptions/untrack/", f.subscription_untrack, name="subscription_untrack"),
    path("review/subscriptions/retrack/", f.subscription_retrack, name="subscription_retrack"),

    path("review/income-sources/", f.review_income_sources, name="review_income_sources"),
    path("review/income-sources/apply/", f.review_income_sources_apply, name="review_income_sources_apply"),
    path("review/income-sources/untracked/", f.untracked_income_sources, name="untracked_income_sources"),
    path("review/income-sources/untrack/", f.income_source_untrack, name="income_source_untrack"),
    path("review/income-sources/retrack/", f.income_source_retrack, name="income_source_retrack"),

    # --- NEW: categories CRUD ---
    path("categories/", f.category_list, name="category_list"),
    path("categories/<int:pk>/edit/", f.category_edit, name="category_edit"),
    path("categories/<int:pk>/delete/", f.category_delete, name="category_delete"),

    path("register/", f.register, name="register"),
    path("login/",  auth_views.LoginView.as_view(template_name="login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),

    path("tx/<int:tx_id>/delete/", f.tx_delete, name="tx_delete"),
    path("tx/<int:tx_id>/restore/", f.tx_restore, name="tx_restore"),
    path("deleted/", f.deleted_list, name="deleted_list"),

    path("profile/", f.profile, name="profile"),
    path("language/set/", settings_views.set_preferred_language, name="set_preferred_language"),
    path("feedback/", settings_views.feedback, name="feedback"),

    # Smart launchers (no AI logic here, just scoping & redirects)
    path("ai/run-uncategorized/", f.ai_run_uncategorized, name="ai_run_uncategorized"),
    path("ai/recheck-all/", f.ai_recheck_all, name="ai_recheck_all"),

    path("reports/", f.reports, name="reports"),
    path("reports/generate/", f.reports_generate, name="reports_generate"),

    path("teach-ai/", f.teach_ai, name="teach_ai"),
    path("onboarding/mark", f.onboarding_mark_done, name="onboarding_mark_done"),

    path("review/ai/", f.review_ai_runs, name="review_ai_runs"),
    path("review/ai/<int:run_id>/", f.review_ai_run_detail, name="review_ai_run_detail"),

    path("ai/dismiss/<int:run_id>/", f.ai_dismiss_notification, name="ai_dismiss_notification"),

    path("assets/", f.assets_dashboard, name="assets_dashboard"),
    path("assets/add/", f.asset_add, name="asset_add"),
    path("assets/<int:pk>/edit/", f.asset_edit, name="asset_edit"),
    path("api/search-asset/", f.api_search_asset, name="api_search_asset"),

    #Profile delation
    path("profile/delete-account/", f.profile_delete_account, name="profile_delete_account"),
    path("profile/cancel-delete-account/", f.profile_cancel_delete_account, name="profile_cancel_delete_account"),
]
