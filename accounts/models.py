from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    # Make email required + unique
    email = models.EmailField("email address", unique=True, blank=False)
    last_active_at = models.DateTimeField(null=True, blank=True, db_index=True, editable=False)

    # Keep username as the login identifier (as you requested)
    USERNAME_FIELD = "username"

    # Required when creating superuser via CLI
    REQUIRED_FIELDS = ["email"]
