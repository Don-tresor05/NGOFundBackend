from django.core.management.base import BaseCommand, CommandError

from apps.reports.models import ReportSchedule
from apps.reports.services import run_due_report_schedules, run_report_schedule


class Command(BaseCommand):
    help = "Dispatch due report schedules through the shared delivery workflow."

    def add_arguments(self, parser):
        parser.add_argument(
            "--schedule-id",
            type=int,
            help="Run a single report schedule by ID instead of processing all due schedules.",
        )

    def handle(self, *args, **options):
        schedule_id = options.get("schedule_id")
        if schedule_id:
            try:
                schedule = ReportSchedule.objects.select_related("created_by").get(pk=schedule_id)
            except ReportSchedule.DoesNotExist as exc:
                raise CommandError(f"Report schedule {schedule_id} does not exist.") from exc

            deliveries = run_report_schedule(schedule, triggered_by=schedule.created_by)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Dispatched {len(deliveries)} report deliveries for schedule {schedule.id}."
                )
            )
            return

        results = run_due_report_schedules()
        total_deliveries = sum(len(result["deliveries"]) for result in results)
        failed_schedules = [result for result in results if result["error"]]

        if failed_schedules:
            for result in failed_schedules:
                self.stderr.write(
                    self.style.WARNING(
                        f"Schedule {result['schedule_id']} ({result['report_type']}): {result['error']}"
                    )
                )

        if total_deliveries == 0:
            self.stdout.write("No due report schedules were processed.")
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {len(results)} schedule(s) and dispatched {total_deliveries} report delivery record(s)."
            )
        )
