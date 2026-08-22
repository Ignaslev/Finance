import time
import requests
import yfinance as yf
import pandas as pd
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model
from finance.models import Asset, AssetHolding, MoneySource, PortfolioSnapshot
from finance.investments import sync_investment_source_balance


class Command(BaseCommand):
    help = "Updates asset prices and saves a history snapshot. Can run in a loop."

    def add_arguments(self, parser):
        parser.add_argument(
            '--loop',
            action='store_true',
            help='Run the updater in an infinite loop (useful for local dev).',
        )
        parser.add_argument(
            '--interval',
            type=int,
            default=600,  # Default: 10 minutes (600 seconds)
            help='Seconds to wait between updates when in loop mode.',
        )

    def handle(self, *args, **options):
        loop = options['loop']
        interval = options['interval']

        if loop:
            self.stdout.write(self.style.SUCCESS(f"--- Starting Asset Updater Service (Interval: {interval}s) ---"))
            self.stdout.write("Press Ctrl+C to stop.")

            while True:
                try:
                    self._run_update()
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"CRITICAL ERROR in loop: {e}"))

                self.stdout.write(f"Sleeping for {interval} seconds...\n")
                time.sleep(interval)
        else:
            # Run once and exit (standard behavior)
            self._run_update()

    def _run_update(self):
        """
        The core logic. Fetches prices and saves snapshots.
        """
        timestamp = timezone.now().strftime('%H:%M:%S')
        self.stdout.write(f"[{timestamp}] Fetching latest prices...")

        # 1. Identify Assets to Update
        held_asset_ids = AssetHolding.objects.values_list('asset_id', flat=True).distinct()
        target_assets = Asset.objects.filter(id__in=held_asset_ids)

        if not target_assets.exists():
            self.stdout.write("No user holdings found. Skipping update.")
            return

        cryptos = target_assets.filter(asset_type='crypto')
        stocks = target_assets.filter(asset_type='stock')

        # 2. Get FX Rate (USD -> EUR)
        usd_eur_rate = Decimal("0.92")
        try:
            fx = yf.Ticker("EUR=X")
            hist = fx.history(period="5d")
            if not hist.empty:
                usd_eur_rate = Decimal(str(hist['Close'].iloc[-1]))
        except:
            pass

        # 3. Update Crypto (CoinGecko)
        if cryptos.exists():
            ids = list(cryptos.values_list('lookup_key', flat=True))
            chunk_size = 50
            for i in range(0, len(ids), chunk_size):
                chunk = ids[i:i + chunk_size]
                id_str = ",".join(chunk)
                url = f"https://api.coingecko.com/api/v3/simple/price?ids={id_str}&vs_currencies=eur"

                try:
                    data = requests.get(url, timeout=10).json()
                    for asset in cryptos.filter(lookup_key__in=chunk):
                        if asset.lookup_key in data:
                            price = Decimal(str(data[asset.lookup_key]['eur']))
                            asset.current_price_eur = price
                            asset.price_updated_at = timezone.now()
                            asset.save()
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"CG Error: {e}"))

        # 4. Update Stocks (Yahoo)
        if stocks.exists():
            tickers = list(stocks.values_list('lookup_key', flat=True))
            try:
                data = yf.download(tickers, period="5d", progress=False)['Close']
                if isinstance(data, pd.Series):
                    data = data.to_frame(name=tickers[0])

                data = data.ffill()  # Fix NaNs
                last_prices = data.iloc[-1]

                for s in stocks:
                    try:
                        raw = last_prices.get(s.lookup_key)
                        if pd.isna(raw): continue

                        price_val = Decimal(str(raw))

                        if "." not in s.lookup_key and "EUR" not in s.lookup_key:
                            s.current_price_eur = price_val * usd_eur_rate
                        else:
                            s.current_price_eur = price_val

                        s.price_updated_at = timezone.now()
                        s.save()
                    except:
                        pass
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"YF Error: {e}"))

        # 5. Recalculate & Snapshot
        User = get_user_model()
        users_with_assets = User.objects.filter(assets__isnull=False).distinct()

        for user in users_with_assets:
            c_total = Decimal("0")
            s_total = Decimal("0")

            holdings = AssetHolding.objects.filter(user=user).select_related('asset')
            for h in holdings:
                # Force reload from DB to ensure we use the price we JUST saved
                h.asset.refresh_from_db()
                val = h.quantity * h.asset.current_price_eur

                if h.asset.asset_type == 'crypto':
                    c_total += val
                else:
                    s_total += val

            # Update every linked investment source, including renamed and
            # localized accounts. Display names are not stable identifiers.
            linked_sources = (
                MoneySource.objects.filter(
                    user=user,
                    type="investment",
                    holdings__isnull=False,
                )
                .prefetch_related("holdings__asset")
                .distinct()
            )
            for source in linked_sources:
                sync_investment_source_balance(source)

            # Save Snapshot
            PortfolioSnapshot.objects.create(
                user=user,
                crypto_total=c_total,
                stock_total=s_total
            )
            self.stdout.write(self.style.SUCCESS(f" > Snapshot for {user.username}: €{c_total + s_total:,.2f}"))
