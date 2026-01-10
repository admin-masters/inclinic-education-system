from __future__ import annotations

from django.db import models
from django.db.models import Q
from django.utils import timezone


def active_window_q(model_cls: type[models.Model]) -> Q:
    """
    Returns a Q() that marks a CampaignCollateral row as active for "today"
    using inclusive day semantics and correct NULL handling.

    Active if:
      (start_date is NULL or start_date <= end_of_today)
    AND
      (end_date   is NULL or end_date >= start_of_today)

    Works for DateField or DateTimeField.
    """

    # Use local "now" so day boundaries match your business timezone.
    now = timezone.localtime(timezone.now())

    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_today = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    start_field = model_cls._meta.get_field("start_date")
    end_field = model_cls._meta.get_field("end_date")

    # If both are DateField (not DateTimeField), filter using dates
    is_datetime = isinstance(start_field, models.DateTimeField) or isinstance(end_field, models.DateTimeField)
    if not is_datetime:
        today = timezone.localdate()
        return (
            (Q(start_date__lte=today) | Q(start_date__isnull=True)) &
            (Q(end_date__gte=today)   | Q(end_date__isnull=True))
        )

    # DateTimeField path
    return (
        (Q(start_date__lte=end_of_today) | Q(start_date__isnull=True)) &
        (Q(end_date__gte=start_of_today) | Q(end_date__isnull=True))
    )
