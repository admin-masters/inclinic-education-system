from __future__ import annotations

from dataclasses import dataclass

from django.utils import timezone

from reporting_etl.models import SourceMigrationBatchV2


ACTIVE_V2_STATUS = "active_v2"
SUPERSEDED_V2_STATUS = "completed_superseded"


@dataclass(frozen=True)
class ActiveV2Batch:
    migration_batch_id: str
    database_name: str
    completed_at: object | None


def get_active_v2_batch() -> ActiveV2Batch | None:
    batch = (
        SourceMigrationBatchV2.objects.filter(system_name="inclinic", status=ACTIVE_V2_STATUS)
        .order_by("-completed_at", "-started_at")
        .first()
    )
    if not batch:
        return None
    return ActiveV2Batch(
        migration_batch_id=batch.migration_batch_id,
        database_name=batch.database_name,
        completed_at=batch.completed_at,
    )


def inclinic_v2_reads_enabled() -> bool:
    return get_active_v2_batch() is not None


def activate_v2_batch(batch_id: str) -> None:
    SourceMigrationBatchV2.objects.filter(system_name="inclinic", status=ACTIVE_V2_STATUS).exclude(
        migration_batch_id=batch_id
    ).update(status=SUPERSEDED_V2_STATUS, notes="Superseded by a newer validated active_v2 batch.")
    SourceMigrationBatchV2.objects.filter(migration_batch_id=batch_id, system_name="inclinic").update(
        status=ACTIVE_V2_STATUS,
        completed_at=timezone.now(),
    )
