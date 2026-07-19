# MoneyCompass — Security Review

**Date:** 2026-07-02
**Scope:** Full codebase (Django project `moneycoach`, apps `accounts` + `finance`), settings, dependencies, templates. Third-party packages in `.venv/` were excluded from manual review; dependencies were checked against known CVEs.

**Overall:** The app is in good shape on the fundamentals most personal-finance apps get wrong. Access control is consistently scoped to `request.user`, there is no raw SQL, output escaping is correct, and redirect targets are validated. The serious issues below are almost all configuration/secret-handling problems, not code-injection flaws. Fix the CRITICAL and HIGH items before treating the app as hardened.

---

## CRITICAL

### C1. Live secrets sit in plaintext `.env` and one is a real key
`.env` contains a real OpenAI key (`sk-proj-…`), Stripe secret + webhook secret, and the Django `SECRET_KEY`. `.env` is correctly git-ignored (verified — not tracked), so it is not in history, but:

- The **OpenAI key is a real production key** in a file on the Desktop. Treat it as compromised the moment it leaves the machine. **Rotate it now** at platform.openai.com, and rotate the Stripe keys/webhook secret too as hygiene.
- The `SECRET_KEY` value begins with `django-insecure-…`. That prefix is the marker Django uses for throwaway dev keys. **Generate a fresh 50-char random key** for production and keep it only in the server's real environment variables, never a file.

**Fix:** Rotate all four secrets. Store production secrets in the host's env (Railway variables), not a checked-out `.env`. Confirm no backup/zip of this folder was ever shared.

### C2. `DJANGO_DEBUG=True` in `.env` + unsigned Stripe webhook = free subscriptions
Two facts combine into an exploitable auth-bypass:

1. `.env` sets `DJANGO_DEBUG=True`.
2. `finance/views/billing.py` `webhook()` does:
   ```python
   if webhook_secret:
       event = stripe.Webhook.construct_event(...)   # verified
   elif settings.DEBUG:
       event = json.loads(payload)                    # UNVERIFIED
   ```

If the app ever runs with this `.env` (DEBUG on), the webhook accepts **forged, unsigned events**. An attacker can POST a fake `customer.subscription.updated` and grant themselves paid access. `DEBUG=True` also disables SSL redirect / secure-cookie defaults (they key off `IS_PROD = not DEBUG`) and leaks full stack traces.

**Fix:** Never run production with `DEBUG=True`. Set `DJANGO_DEBUG=False` in the real environment. Additionally, remove the `elif settings.DEBUG` branch or guard it so it can never run outside local dev — the webhook should hard-fail (400) when no signature secret is configured, regardless of DEBUG.

---

## HIGH

### H1. Outdated dependencies with known CVEs
- **Django 5.2.7** — multiple security releases have shipped since (5.2.11 through **5.2.15**, June 2026), fixing SQL-injection and DoS issues. Upgrade to the latest 5.2.x.
- **gunicorn 21.2.0** — vulnerable to HTTP request smuggling (**CVE-2024-6827**, TE.CL, CVSS 7.5). Fixed in **23.0.0**. Upgrade.

**Fix:** `pip install --upgrade "Django>=5.2.15" "gunicorn>=23.0.0"`, re-run tests, redeploy. Then schedule a recurring dependency scan (`pip-audit`).

---

## MEDIUM

### M1. Login/registration throttling is per-process only
`accounts/throttling.py` uses Django's default cache. No cache backend is configured, so it falls back to **LocMemCache**, which is per-process. With multiple gunicorn workers the rate limits (login 25/IP, register 20/IP, etc.) are effectively multiplied by the worker count and reset on restart — weak brute-force protection.

**Fix:** Configure a shared cache (Redis/Memcached, or DB cache) in `CACHES` so throttling counts are global.

### M2. No throttle on password-reset endpoint
`password_reset` uses Django's built-in view with no rate limiting, unlike login/register. Enables email-enumeration and email-bombing of arbitrary addresses.

**Fix:** Apply the same `throttling` helper (per-IP and per-email) to the password-reset POST.

### M3. `client_ip` trusts `REMOTE_ADDR` only — behind a proxy this is the proxy IP
On Railway/behind a load balancer, `REMOTE_ADDR` is the proxy, so **all users share one throttle bucket** (over-blocking) — or, if you later switch to reading `X-Forwarded-For` naively, attackers spoof it. `SECURE_PROXY_SSL_HEADER` is set, confirming a proxy is in front.

**Fix:** Read the correct client IP from the trusted proxy's forwarded header, validating the proxy chain — don't naively trust `X-Forwarded-For`.

---

## LOW / Hardening

- **L1. `CSRF_COOKIE_HTTPONLY = False`** (settings.py:219). Intentional-looking, but the CSRF token is not read by JS anywhere here; setting it `True` is slightly safer. Minor.
- **L2. `SECURE_HSTS_SECONDS` defaults to 60.** Once HTTPS is stable, raise to 31536000 with `INCLUDE_SUBDOMAINS`/`PRELOAD`.
- **L3. Placeholder admin address** `ADMINS = [... "yourgmail@gmail.com"]`. Set a real address or admin error mail goes nowhere.
- **L4. `BETA_ACCESS_CODE` shipped in `.env`** (`noriutestuot`) and compared in plaintext. Fine for a beta gate; just don't treat it as a security boundary.
- **L5. Broad `except: pass` blocks** (Bandit flagged ~20, all Low). Mostly around email sending and parsing where swallowing is intentional. Not vulnerabilities, but they can hide errors — prefer logging.
- **L6. SHA1 in `build_fingerprint_v2`** (utils.py:108). Used only for de-dup, not security — Bandit flags it High by default but it is a **false positive here**. Add `usedforsecurity=False` to silence it.
- **L7. `pandas.read_excel` on uploaded files.** Size- and row-limited already (good). openpyxl is the engine; keep it patched. Low risk.

---

## Verified GOOD (no action needed)

- **Access control / IDOR:** Every object fetch is scoped — `get_object_or_404(..., user=request.user)` and `.filter(user=request.user)` throughout transactions, categories, assets, goals, reports. Sensitive actions (account/data deletion) require password re-entry. No horizontal privilege issues found.
- **SQL injection:** No raw SQL, `.raw()`, `.extra()`, or cursor use. All queries go through the ORM with parameterized filters.
- **XSS:** Templates escape by default. Dynamic JSON is passed as `JSON.parse('{{ x|escapejs }}')` — correct. `|safe` appears only on Django-generated password help text; `format_html` is used properly with placeholders. No `autoescape off`.
- **Open redirect:** `_safe_next_url` uses `url_has_allowed_host_and_scheme` against the request host before redirecting.
- **CSRF:** Enabled globally; all state-changing forms carry `{% csrf_token %}`. The one `@csrf_exempt` (Stripe webhook) is required and otherwise gated by signature (see C2).
- **Auth:** Email login backend uses `check_password` + `user_can_authenticate`; registration requires email verification (`is_active=False`); Django password validators enabled.
- **Secrets not in git:** `.env` and `db.sqlite3` are git-ignored and untracked (verified).

---

## Priority checklist

1. Rotate OpenAI + Stripe secrets; generate a real `SECRET_KEY`. **(C1)**
2. Set `DJANGO_DEBUG=False` in prod and remove the DEBUG webhook-bypass branch. **(C2)**
3. Upgrade Django to ≥5.2.15 and gunicorn to ≥23.0.0. **(H1)**
4. Add a shared cache backend and throttle password reset. **(M1, M2)**
5. Fix client-IP handling behind the proxy. **(M3)**
