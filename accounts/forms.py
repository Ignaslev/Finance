from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm

User = get_user_model()


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(required=True, max_length=150)
    last_name = forms.CharField(required=True, max_length=150)

    class Meta(UserCreationForm.Meta):
        model = User
        # IMPORTANT: no "username" here — we will auto-set it from email
        fields = ("first_name", "last_name", "email", "password1", "password2")

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("This email is already in use.")
        return email

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
