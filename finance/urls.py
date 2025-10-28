from django.urls import path
from django.contrib.auth import views as auth_views
from . import views as f

urlpatterns = [
    path("", f.upload, name="upload"),
    path("overview/", f.overview, name="overview"),
    path("upload/", f.upload, name="upload"),

    path("env-check/", f.env_check, name="env_check"),

    path("uncategorized/", f.uncategorized, name="uncategorized"),
    path("tx/<int:pk>/edit/", f.tx_edit, name="tx_edit"),

# NEW: auto-categorize endpoint (runs only when you click)
    path("ai/full/", f.ai_full_categorize, name="ai_full_categorize"),

# NEW review pages
    path("review/low/", f.review_low_conf, name="review_low_conf"),
    path("review/low/apply/", f.review_low_apply, name="review_low_apply"),
    path("review/ai/", f.review_ai_recent, name="review_ai_recent"),

    # --- NEW: categories CRUD ---
    path("categories/", f.category_list, name="category_list"),
    path("categories/<int:pk>/edit/", f.category_edit, name="category_edit"),
    path("categories/<int:pk>/delete/", f.category_delete, name="category_delete"),

    path("register/", f.register, name="register"),
    path("login/",  auth_views.LoginView.as_view(template_name="login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    path("tx/<int:tx_id>/delete/", f.tx_delete, name="tx_delete"),
    path("tx/<int:tx_id>/restore/", f.tx_restore, name="tx_restore"),
    path("deleted/", f.deleted_list, name="deleted_list"),

    path("profile/", f.profile, name="profile"),
]
