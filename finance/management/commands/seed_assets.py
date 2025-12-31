import math
import time
import requests
from bs4 import BeautifulSoup

from django.core.management.base import BaseCommand
from django.utils import timezone

from finance.models import Asset


class Command(BaseCommand):
    help = "Seeds the database with Cryptos (CoinGecko), S&P 500 stocks (Wikipedia), and common ETFs."

    def add_arguments(self, parser):
        parser.add_argument("--cryptos", type=int, default=250, help="How many top cryptos to seed (max practical: ~2000+).")
        parser.add_argument("--seed-sp500", action="store_true", help="Seed S&P 500 tickers from Wikipedia.")
        parser.add_argument("--seed-etfs", action="store_true", help="Seed curated ETF list.")
        parser.add_argument("--sleep", type=float, default=1.2, help="Sleep seconds between CoinGecko page requests (avoid rate limits).")

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Starting Asset Seed..."))

        if options["cryptos"] > 0:
            self.seed_cryptos(limit=options["cryptos"], sleep_s=options["sleep"])

        if options["seed_sp500"]:
            self.seed_sp500()

        if options["seed_etfs"]:
            self.seed_etfs()

        self.stdout.write(self.style.SUCCESS("Done."))

    # -------------------------
    # 1) CRYPTOS (CoinGecko)
    # -------------------------
    def seed_cryptos(self, limit: int, sleep_s: float):
        self.stdout.write(f"Fetching Top {limit} Cryptos from CoinGecko...")

        per_page = 250
        pages = max(1, math.ceil(limit / per_page))
        total_upserts = 0

        url = "https://api.coingecko.com/api/v3/coins/markets"

        for page in range(1, pages + 1):
            params = {
                "vs_currency": "eur",
                "order": "market_cap_desc",
                "per_page": per_page,
                "page": page,
                "sparkline": "false",
            }

            try:
                r = requests.get(url, params=params, timeout=20)
                if r.status_code != 200:
                    self.stdout.write(self.style.ERROR(f"CoinGecko API failed page={page}: {r.status_code} {r.text[:200]}"))
                    break

                data = r.json()
                if not data:
                    break

                for item in data:
                    # lookup_key for crypto = CoinGecko ID (e.g. "bitcoin")
                    Asset.objects.update_or_create(
                        lookup_key=item["id"],
                        defaults={
                            "symbol": (item.get("symbol") or "").upper(),
                            "name": item.get("name") or item["id"],
                            "asset_type": "crypto",
                            "current_price_eur": item.get("current_price"),
                            "price_updated_at": timezone.now(),
                        },
                    )
                    total_upserts += 1
                    if total_upserts >= limit:
                        break

                self.stdout.write(self.style.SUCCESS(f"Seeded crypto page {page}/{pages} (total={total_upserts})."))

                if total_upserts >= limit:
                    break

                time.sleep(sleep_s)

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Crypto seed error on page={page}: {e}"))
                break

        self.stdout.write(self.style.SUCCESS(f"Crypto seeding complete (total={total_upserts})."))

    # -------------------------
    # 2) STOCKS (S&P 500 via Wikipedia)
    # -------------------------
    def seed_sp500(self):
        self.stdout.write("Fetching S&P 500 tickers from Wikipedia...")

        # Wikipedia page contains a table with Symbol/Security etc. :contentReference[oaicite:1]{index=1}
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

        try:
            r = requests.get(url, timeout=20, headers={"User-Agent": "moneycoach-seeder/1.0"})
            r.raise_for_status()

            soup = BeautifulSoup(r.text, "html.parser")

            # Find the first "wikitable" that has "Symbol" header
            tables = soup.find_all("table", class_="wikitable")
            sp_table = None
            for t in tables:
                header = t.find("tr")
                if header and "Symbol" in header.get_text():
                    sp_table = t
                    break

            if not sp_table:
                raise RuntimeError("Could not locate S&P 500 table on Wikipedia page.")

            rows = sp_table.find_all("tr")[1:]  # skip header
            count = 0

            for row in rows:
                cols = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
                if len(cols) < 2:
                    continue

                symbol = cols[0].strip()
                name = cols[1].strip()

                # Yahoo/most finance APIs use "-" for share-class tickers (e.g., BRK.B -> BRK-B)
                symbol_norm = symbol.replace(".", "-")

                Asset.objects.update_or_create(
                    lookup_key=symbol_norm,
                    defaults={
                        "symbol": symbol_norm,
                        "name": name,
                        "asset_type": "stock",  # keep as stock
                    },
                )
                count += 1

            self.stdout.write(self.style.SUCCESS(f"S&P 500 seeded/updated: {count} tickers."))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"S&P 500 seed error: {e}"))

    # -------------------------
    # 3) ETFs (curated list)
    # -------------------------
    def seed_etfs(self):
        self.stdout.write("Seeding curated ETFs...")

        # Keep ETFs under asset_type='stock' if your model doesn’t have 'etf'.
        # If you DO have 'etf' choice, change below to asset_type='etf'.
        etfs = [
            # US (very common)
            ("SPY", "SPDR S&P 500 ETF Trust"),
            ("IVV", "iShares Core S&P 500 ETF"),
            ("VOO", "Vanguard S&P 500 ETF"),
            ("VTI", "Vanguard Total Stock Market ETF"),
            ("QQQ", "Invesco QQQ Trust"),
            ("IWM", "iShares Russell 2000 ETF"),
            ("VEA", "Vanguard FTSE Developed Markets ETF"),
            ("VWO", "Vanguard FTSE Emerging Markets ETF"),
            ("BND", "Vanguard Total Bond Market ETF"),
            ("AGG", "iShares Core U.S. Aggregate Bond ETF"),
            ("TLT", "iShares 20+ Year Treasury Bond ETF"),
            ("LQD", "iShares iBoxx $ Investment Grade Corporate Bond ETF"),
            ("HYG", "iShares iBoxx $ High Yield Corporate Bond ETF"),
            ("GLD", "SPDR Gold Shares"),
            ("SLV", "iShares Silver Trust"),

            # UCITS / Europe-friendly (common for EU investors)
            ("VWCE.DE", "Vanguard FTSE All-World UCITS ETF (Acc)"),
            ("VWRL.L", "Vanguard FTSE All-World UCITS ETF (Dist)"),
            ("IWDA.AS", "iShares Core MSCI World UCITS ETF"),
            ("EIMI.L", "iShares Core MSCI EM IMI UCITS ETF"),
            ("CSPX.L", "iShares Core S&P 500 UCITS ETF"),
            ("VUAA.L", "Vanguard S&P 500 UCITS ETF (Acc)"),
            ("SXR8.DE", "iShares Core S&P 500 UCITS ETF (Xetra)"),
            ("EUNL.DE", "iShares Core MSCI World UCITS ETF (Xetra)"),
        ]

        count = 0
        for ticker, name in etfs:
            Asset.objects.update_or_create(
                lookup_key=ticker,
                defaults={
                    "symbol": ticker,
                    "name": name,
                    "asset_type": "stock",
                },
            )
            count += 1
        self.stdout.write(self.style.SUCCESS(f"ETFs seeded/updated: {count} tickers."))
