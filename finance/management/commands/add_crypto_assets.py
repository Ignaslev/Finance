import requests
from django.core.management.base import BaseCommand
from django.utils import timezone

from finance.models import Asset


class Command(BaseCommand):
    help = "Add or update specific crypto assets by CoinGecko ID(s)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--ids",
            required=True,
            help="Comma-separated CoinGecko IDs, e.g. astar,alchemy-pay,stronghold",
        )
        parser.add_argument(
            "--vs",
            default="eur",
            help="Fiat currency for price (default: eur).",
        )

    def handle(self, *args, **options):
        ids_raw = (options.get("ids") or "").strip()
        vs = (options.get("vs") or "eur").strip().lower()

        ids = [x.strip() for x in ids_raw.split(",") if x.strip()]
        if not ids:
            self.stdout.write(self.style.ERROR("No IDs provided."))
            return

        self.stdout.write(f"Fetching {len(ids)} crypto assets from CoinGecko (vs={vs})...")

        # CoinGecko markets endpoint supports explicit ids list
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": vs,
            "ids": ",".join(ids),
            "order": "market_cap_desc",
            "per_page": len(ids),
            "page": 1,
            "sparkline": "false",
        }

        try:
            r = requests.get(url, params=params, timeout=20)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"CoinGecko request failed: {e}"))
            return

        # Map returned data by id
        by_id = {item.get("id"): item for item in data if item.get("id")}

        created = 0
        updated = 0
        missing = []

        for cg_id in ids:
            item = by_id.get(cg_id)
            if not item:
                missing.append(cg_id)
                continue

            obj, was_created = Asset.objects.update_or_create(
                lookup_key=item["id"],  # crypto lookup_key = CoinGecko ID
                defaults={
                    "symbol": (item.get("symbol") or "").upper(),
                    "name": item.get("name") or item["id"],
                    "asset_type": "crypto",
                    "current_price_eur": item.get("current_price") or 0,
                    "price_updated_at": timezone.now(),
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(f"Done. Created: {created}, Updated: {updated}"))
        if missing:
            self.stdout.write(self.style.WARNING(f"CoinGecko returned no data for: {', '.join(missing)}"))
