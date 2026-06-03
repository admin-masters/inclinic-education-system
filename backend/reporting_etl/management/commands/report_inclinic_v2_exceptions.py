from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db.models import Count

from reporting_etl.models import MigrationExceptionV2


class Command(BaseCommand):
    help = "Print grouped open exceptions from the InClinic v2 migration layer."

    def add_arguments(self, parser):
        parser.add_argument("--batch-id", default="")
        parser.add_argument("--limit", type=int, default=20)

    def handle(self, *args, **options):
        qs = MigrationExceptionV2.objects.filter(system_name="inclinic", resolution_status="open")
        if options["batch_id"].strip():
            qs = qs.filter(migration_batch_id=options["batch_id"].strip())

        self.stdout.write("Open InClinic v2 exceptions by issue_code")
        for row in qs.values("issue_code").annotate(count=Count("exception_id")).order_by("-count", "issue_code"):
            self.stdout.write(f"{row['issue_code']}: {row['count']}")

        self.stdout.write("")
        self.stdout.write("Sample exceptions")
        for exc in qs.order_by("-exception_id")[: options["limit"]]:
            self.stdout.write(
                f"{exc.exception_id} | {exc.issue_code} | {exc.source_table} | "
                f"{exc.source_pk_value} | {exc.issue_details[:240]}"
            )
