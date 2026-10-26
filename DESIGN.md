# MoneyCompass — Design

The approved look is the existing one: `moneycoach/static/css/main.css` + `redesign.css`. Keep it. New screens reuse its classes and tokens instead of introducing a new style. (A full restyle was tried on 2026-10-25 and rejected as less clear.)

## What makes it work
- **Type:** Inter, heavy weights for headings and key numbers (800), uppercase letter-spaced labels above hero numbers ("GRYNASIS TURTAS").
- **Hero number first:** the overview leads with net worth, the asset mix bar and the net worth history chart. Do not demote them.
- **Color:** brand teal `--primary-teal` (#00b593) / `--primary-teal-dark`, pale teal surfaces `--mc-teal-soft` / `--mc-teal-pale`, page `--bg-body` (#edf1f5), ink `--text-dark` (#14233a).
- **Cards:** `.card` — white, 18px radius, soft shadow, 24px padding. Two-column card grid on desktop.
- **Controls:** `.btn .btn-primary` teal buttons; pill switches use `.language-switch` (also used for the bank tabs on the first-run screen); numbered steps use `.onboarding-intro-steps`.
- **Icons:** Phosphor.

## First-run screen (accounts with no transactions)
`overview.html` shows one centered card (mascot, uppercase label, big headline, upload dropzone, privacy note) plus a "how to get your statement" card with bank tabs, instead of empty charts. The setup banner is hidden there because that screen is the step. Upload errors return to it with a plain message.

## Gotchas
- LT `floatformat` writes decimal commas; never feed it into CSS values (use `stringformat`).
- `locale/lt/LC_MESSAGES/django.po` has a duplicate msgid, so `msgfmt` fails; new strings use the inline `{% if is_lt %}` / `LANGUAGE_CODE` pattern until the catalog is cleaned.

## Local preview
Run the app against a separate demo database (AI and analytics off), in PowerShell from the project folder:

```
$env:DJANGO_DEBUG="1"; $env:DATABASE_URL="sqlite:///demo.sqlite3"; $env:OPENAI_API_KEY=""; $env:GOOGLE_ANALYTICS_MEASUREMENT_ID=""; $env:META_PIXEL_ID=""
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py seed_demo
.venv\Scripts\python manage.py runserver 8020
```

Open http://127.0.0.1:8020/accounts/login/ and sign in as `new@moneycompass.test` (empty, first-run screen) or `demo@moneycompass.test` (three months of data). The password is `DEMO_PASSWORD` in `finance/management/commands/seed_demo.py`. Re-run `seed_demo` to reset both accounts.
