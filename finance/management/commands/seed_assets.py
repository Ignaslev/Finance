import requests
import time
from django.core.management.base import BaseCommand
from django.utils import timezone
from finance.models import Asset


class Command(BaseCommand):
    help = "Seeds the local database with Top Cryptos and common Stocks."

    def handle(self, *args, **options):
        self.stdout.write("Starting Asset Seed...")

        # --- 1. Seed Top 250 Cryptos from CoinGecko ---
        self.stdout.write("Fetching Top 250 Cryptos...")
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "eur",
            "order": "market_cap_desc",
            "per_page": 250,
            "page": 1,
            "sparkline": "false"
        }

        try:
            r = requests.get(url, params=params, timeout=10)
            if r.status_code == 200:
                data = r.json()
                count = 0
                for item in data:
                    # Create or Update the asset
                    # lookup_key for crypto = CoinGecko ID (e.g. "bitcoin")
                    obj, created = Asset.objects.update_or_create(
                        lookup_key=item['id'],
                        defaults={
                            'symbol': item['symbol'].upper(),
                            'name': item['name'],
                            'asset_type': 'crypto',
                            'current_price_eur': item['current_price'],
                            'price_updated_at': timezone.now()
                        }
                    )
                    count += 1
                self.stdout.write(self.style.SUCCESS(f"Successfully seeded {count} cryptos."))
            else:
                self.stdout.write(self.style.ERROR(f"CoinGecko API failed: {r.status_code}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Crypto seed error: {e}"))

        # --- 2. Seed Common Stocks (Manual List) ---
        # Since Yahoo doesn't give a "Top List" easily, we seed common ones.
        # Users can still add others manually later if we keep the live search fallback,
        # but for now let's rely on a solid local list.
        common_stocks = [
            ("AAPL", "Apple Inc."),
            ("MSFT", "Microsoft Corp"),
            ("GOOGL", "Alphabet Inc."),
            ("AMZN", "Amazon.com"),
            ("TSLA", "Tesla Inc."),
            ("NVDA", "NVIDIA Corp"),
            ("VWCE.DE", "Vanguard FTSE All-World"),
            ("IWDA.AS", "iShares Core MSCI World"),
            ("SPY", "SPDR S&P 500 ETF"),
            ("O", "Realty Income Corp"),
        ]

        self.stdout.write("Seeding common Stocks...")
        for ticker, name in common_stocks:
            Asset.objects.get_or_create(
                lookup_key=ticker,
                defaults={
                    'symbol': ticker,
                    'name': name,
                    'asset_type': 'stock'
                }
            )
        self.stdout.write(self.style.SUCCESS("Common stocks seeded."))