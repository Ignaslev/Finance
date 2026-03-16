from django.core.management.base import BaseCommand
from django.db import transaction as db_transaction
from django.utils import timezone

from finance.models import PendingDataDeletion, Transaction, ImportBatch, AiRun


class Command(BaseCommand):
    help = "Process scheduled data deletions."

    def handle(self, *args, **options):
        now = timezone.now()
        qs = (
            PendingDataDeletion.objects
            .select_related("user")
            .filter(
                scheduled_for__isnull=False,
                canceled_at__isnull=True,
                scheduled_for__lte=now,
            )
            .order_by("scheduled_for")
        )

        processed = 0

        for req in qs:
            try:
                with db_transaction.atomic():
                    if req.scope == PendingDataDeletion.SCOPE_TRANSACTIONS:
                        tx_qs = Transaction.objects.filter(user=req.user)
                        batch_qs = ImportBatch.objects.filter(user=req.user)
                        run_qs = AiRun.objects.filter(user=req.user)

                        tx_count = tx_qs.count()
                        batch_count = batch_qs.count()
                        run_count = run_qs.count()

                        run_qs.delete()
                        tx_qs.delete()
                        batch_qs.delete()

                        self.stdout.write(self.style.SUCCESS(
                            f"Deleted user {req.user_id} transactions={tx_count} import_batches={batch_count} ai_runs={run_count}"
                        ))
                    else:
                        self.stdout.write(
                            self.style.WARNING(f"Unknown data deletion scope for request {req.id}: {req.scope}")
                        )
                        continue

                    req.delete()
                    processed += 1

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"Failed processing data deletion for user {req.user_id}: {e}")
                )

        self.stdout.write(f"Done. Processed: {processed}")