import requests
from django.core.management.base import BaseCommand
from django.utils import timezone
from finance.models import CryptoAsset, AssetHolding, MoneySource


class Command(BaseCommand):
    help = "Fetches top crypto prices from CoinGecko and updates user balances."

    def handle(self, *args, **options):
        # 1. Get list of CoinGecko IDs we are tracking
        # (For MVP, we auto-seed the top 50 if empty)
        if not CryptoAsset.objects.exists():
            self.stdout.write("Seeding top 50 cryptos...")
            self.seed_top_coins()

        assets = list(CryptoAsset.objects.all())
        ids = ",".join([a.id_name for a in assets])

        if not ids:
            self.stdout.write("No assets to track.")
            return

        # 2. Fetch Prices (EUR)
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=eur"
        try:
            r = requests.get(url, timeout=10)
            data = r.json()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"API Error: {e}"))
            return

        # 3. Update Assets
        updated_count = 0
        for asset in assets:
            if asset.id_name in data:
                price = data[asset.id_name].get('eur', 0)
                asset.current_price = price
                asset.price_updated_at = timezone.now()
                asset.save()
                updated_count += 1

        self.stdout.write(self.style.SUCCESS(f"Updated prices for {updated_count} assets."))

        # 4. Update Virtual Account Balances
        # This loops through accounts that have holdings and updates their 'manual_balance'
        # to match the sum of their crypto assets.
        sources_with_crypto = MoneySource.objects.filter(holdings__isnull=False).distinct()

        for source in sources_with_crypto:
            total_value = 0
            for holding in source.holdings.all():
                # Reload asset to get new price
                total_value += (holding.quantity * holding.asset.current_price)

            source.manual_balance = total_value
            source.balance_updated_at = timezone.now()
            source.save()
            self.stdout.write(f"Updated {source.name} balance to {total_value:.2f} EUR")

    def seed_top_coins(self):
        """Auto-populates the DB with top coins so the user has something to choose."""
        url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=eur&order=market_cap_desc&per_page=50&page=1"
        try:
            data = requests.get(url, timeout=10).json()
            for item in data:
                CryptoAsset.objects.get_or_create(
                    id_name=item['id'],
                    defaults={
                        'symbol': item['symbol'].upper(),
                        'name': item['name'],
                        'current_price': item['current_price'],
                        'image_url': item['image'],
                        'rank': item['market_cap_rank']
                    }
                )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Seeding failed: {e}"))