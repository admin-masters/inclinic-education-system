#!/usr/bin/env python
import os
import sys
import django

# Set up Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inclinic_education_system.settings')
django.setup()

from user_management.models import User

# Check field representatives
field_reps = User.objects.filter(role='field_rep').values('id', 'username', 'email', 'field_id')
print('Field Representatives in database:')
for rep in field_reps:
    print(f'ID: {rep["id"]}, Username: {rep["username"]}, Email: {rep["email"]}, Field ID: {rep["field_id"]}')
