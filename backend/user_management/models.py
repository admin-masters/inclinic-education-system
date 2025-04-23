# user_management/models.py

from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('field_rep', 'Field Representative'),
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='field_rep')
    google_auth_id = models.CharField(max_length=255, blank=True, null=True, unique=True)
    phone = models.CharField(max_length=20, blank=True, null=True, unique=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.username} ({self.role})"