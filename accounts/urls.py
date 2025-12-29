from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views

from .views import register, activate
from .forms import EmailAuthenticationForm

urlpatterns = [
    path("register/", register, name="register"),
    path("activate/<uidb64>/<token>/", activate, name="accounts_activate"),

    path("login/", auth_views.LoginView.as_view(
        template_name="accounts/login.html",
        authentication_form=EmailAuthenticationForm
    ), name="login"),

    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    # Password reset flow (emails will work once EMAIL_BACKEND is configured)
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="accounts/password_reset_form.html",
            success_url=reverse_lazy("password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="accounts/password_reset_done.html",
        ),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html",
            success_url=reverse_lazy("password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="accounts/password_reset_complete.html",
        ),
        name="password_reset_complete",
    ),
]
