from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from finance.models import UserProfile
from django.utils.translation import gettext_lazy as _
from .throttling import client_ip, clear_attempts, is_limited, record_attempt

User = get_user_model()


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(required=True, max_length=150)
    last_name = forms.CharField(required=True, max_length=150)
    preferred_language = forms.ChoiceField(
        label=_("Language"),
        choices=UserProfile.LANGUAGE_CHOICES,
        initial=UserProfile.LANG_LT,
        required=True,
    )
    beta_access_code = forms.CharField(
        label=_("Beta code"),
        required=True,
        max_length=100,
    )

    class Meta(UserCreationForm.Meta):
        model = User
        # IMPORTANT: no "username" here — we will auto-set it from email
        fields = ("first_name", "last_name", "email", "password1", "password2")

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_("This email is already in use."))
        return email

    def clean_beta_access_code(self):
        code = (self.cleaned_data.get("beta_access_code") or "").strip()
        expected = (getattr(settings, "BETA_ACCESS_CODE", "") or "").strip()

        if not getattr(settings, "BETA_REGISTRATION_ENABLED", True):
            raise forms.ValidationError(_("Beta registration is currently closed."))

        if not expected or code != expected:
            raise forms.ValidationError(_("Invalid beta code."))

        return code

    def clean(self):
        cleaned = super().clean()

        beta_count = UserProfile.objects.filter(
            is_beta_tester=True,

            user__is_staff=False,
            user__is_superuser=False,
        ).count()

        if beta_count >= getattr(settings, "BETA_USER_LIMIT", 100):
            raise forms.ValidationError(_("Beta is currently full."))

        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)

        email = (self.cleaned_data.get("email") or "").strip().lower()
        user.email = email

        # Your User model still likely has username; keep it consistent:
        if hasattr(user, "username"):
            user.username = email

        user.first_name = (self.cleaned_data.get("first_name") or "").strip()
        user.last_name = (self.cleaned_data.get("last_name") or "").strip()

        # OPTIONAL: allow disabling activation for Railway testing
        require_verify = getattr(settings, "REQUIRE_EMAIL_VERIFICATION", True)
        user.is_active = not require_verify

        if commit:
            user.save()
        return user


class EmailAuthenticationForm(AuthenticationForm):
    """
    We keep the field name 'username' because AuthenticationForm expects it,
    but we label it as Email and our backend treats it as email.
    """
    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={"autofocus": True})
    )

    def clean(self):
        email = (self.cleaned_data.get("username") or "").strip().lower()
        ip = client_ip(self.request)

        if is_limited("login-ip", ip, limit=25, window_seconds=15 * 60):
            raise forms.ValidationError(_("Too many login attempts. Please try again later."))
        if email and is_limited("login-email", email, limit=10, window_seconds=15 * 60):
            raise forms.ValidationError(_("Too many login attempts. Please try again later."))

        try:
            cleaned = super().clean()
        except forms.ValidationError:
            record_attempt("login-ip", ip, window_seconds=15 * 60)
            if email:
                record_attempt("login-email", email, window_seconds=15 * 60)
            raise

        clear_attempts("login-ip", ip)
        if email:
            clear_attempts("login-email", email)
        return cleaned
