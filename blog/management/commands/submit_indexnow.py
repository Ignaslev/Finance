from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from moneycoach.indexnow import key_location, submit_urls
from moneycoach.seo import public_sitemap_paths


class Command(BaseCommand):
    help = "Submit public MoneyCompass URLs to IndexNow."

    def add_arguments(self, parser):
        parser.add_argument(
            "--url",
            action="append",
            dest="urls",
            help="A canonical URL or root-relative path. Repeat for multiple URLs.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the URLs without contacting IndexNow.",
        )

    def handle(self, *args, **options):
        urls = options["urls"] or public_sitemap_paths()
        absolute_urls = [
            url if url.startswith(("http://", "https://")) else f"{settings.SITE_URL.rstrip('/')}{url}"
            for url in urls
        ]

        self.stdout.write(f"IndexNow key location: {key_location()}")
        for url in absolute_urls:
            self.stdout.write(f"  {url}")

        if options["dry_run"]:
            self.stdout.write(self.style.SUCCESS(f"Dry run: {len(absolute_urls)} URLs ready."))
            return

        try:
            status, submitted = submit_urls(absolute_urls)
        except Exception as exc:
            raise CommandError(f"IndexNow submission failed: {exc}") from exc

        if status not in {200, 202}:
            raise CommandError(f"IndexNow returned HTTP {status}.")
        self.stdout.write(
            self.style.SUCCESS(f"IndexNow accepted {len(submitted)} URLs (HTTP {status}).")
        )
