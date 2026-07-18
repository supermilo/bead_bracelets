# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

## Project overview

Django 4.2.15 project (`bracelet_builder`) for building and purchasing a bracelet/jewelry configurator. PostgreSQL is the database backend. Three apps:

- `configurator` — the bracelet-building UI: browsing beads, an anonymous session-based build tray, size selection, and the pre-payment checkout form.
- `checkout` — `Order`/`OrderItem` models and the post-payment order confirmation page.
- `payment` — the unified payment-dispatch flow across three gateways (Stripe, PayPal, MercadoPago), plus the Celery task that emails a PDF receipt.

There is no reference README beyond this file.

## Environment

Dependencies are managed with `pipenv` (`Pipfile` / `Pipfile.lock` at the repo root), not a project-local `.venv`. The virtualenv lives outside the repo, keyed off the repo's path:

```bash
pipenv install          # install/sync dependencies from Pipfile.lock
pipenv shell             # activate the virtualenv
pipenv run <command>     # run a one-off command inside the virtualenv
pipenv --venv            # print the virtualenv path
```

Current dependencies: `django==4.2.15`, `psycopg2-binary`, `pillow`, `stripe`, `mercadopago`, `celery`, `redis`, `weasyprint`, `requests`, `python-decouple`.

`weasyprint` (PDF receipt generation) needs system libs (pango, cairo, gdk-pixbuf) present on the host — not a pure-Python install.

## Configuration (.env)

Most non-database settings are read via `python-decouple`'s `config()` in `bracelet_builder/settings.py` — Celery broker/result-backend URLs, `SITE_PROTOCOL`/`SITE_DOMAIN`, all Stripe/PayPal/MercadoPago keys, `EMAIL_*` (backend/host/port/TLS/credentials), `DEFAULT_FROM_EMAIL`, and `ADMINS`. Two files at the repo root:

- `.env` — real local values (git-ignored). Payment gateway keys are blank by default (no real merchant credentials in dev); email defaults to the console backend unless `EMAIL_BACKEND`/`EMAIL_HOST`/etc. are set to real SMTP values (e.g. Gmail + an app password).
- `.env.example` — placeholder template with the same keys; copy to `.env` for a fresh checkout.

`ADMINS` is parsed from a comma-separated string into a **plain list of email strings**, not Django's usual list of `(name, email)` tuples — fine while `DEBUG=True` (the built-in 500-error mailer that actually needs the tuple shape is inactive in debug mode), but would need converting back to tuples if `DEBUG` is ever `False` and that mailer is needed. `payment.tasks.send_order_confirmation_email`'s admin-notification logic already defensively handles either shape.

`DATABASES` is the one deliberate exception — still hardcoded directly in `settings.py` (see Database section below), not read from `.env`. Don't "fix" this inconsistency without being asked; it's intentional, matching the style of the reference project this was scaffolded from.

`ALLOWED_HOSTS` in `settings.py` also hardcodes an ngrok free-tier hostname alongside `localhost`/`127.0.0.1` — PayPal and MercadoPago webhooks need a publicly reachable callback URL, which `runserver` alone can't provide, so an ngrok tunnel is the dev-time stand-in. `CSRF_TRUSTED_ORIGINS` is read from `.env` (empty by default) for the same reason if the tunnel URL needs CSRF-trusted POSTs.

## Common commands

All commands run from the repo root (where `manage.py` lives), via `pipenv run`:

```bash
pipenv run python manage.py runserver
pipenv run python manage.py makemigrations
pipenv run python manage.py migrate
pipenv run python manage.py createsuperuser
pipenv run python manage.py check
pipenv run python manage.py test                      # full test suite
pipenv run python manage.py test configurator          # single app
pipenv run python manage.py test configurator.tests.TestClassName.test_method   # single test

pipenv run celery -A bracelet_builder worker --loglevel=info   # run the Celery worker
```

There are currently no automated tests in any app (`configurator/tests.py` is Django's default stub; `checkout` and `payment` don't even have a `tests.py`) — verification so far has been done ad hoc via Django's test `Client` in `manage.py shell` scripts, not a committed test suite.

## Database

`bracelet_builder/settings.py` hardcodes PostgreSQL credentials directly in the `DATABASES` dict (no `decouple`/`environ`/env-var indirection — this matches the style of the reference project this was scaffolded from, and is unrelated to the `.env`-based config used for everything else, see Configuration above). Local Postgres must have a matching user and the target database created before running migrations:

```bash
createdb -U postgres -h localhost bracelet_builder_db
# or:
psql -U postgres -h localhost -c "CREATE DATABASE bracelet_builder_db;"
```

If the DB name, user, host, or port are changed for a given environment, update the `DATABASES["default"]` dict in `settings.py` directly (not an env file).

## Background tasks (Celery)

`bracelet_builder/celery.py` bootstraps `Celery('bracelet_builder')`; `bracelet_builder/__init__.py` imports it as `celery_app` so `@shared_task` autodiscovery works.

- **Broker**: RabbitMQ, on this project's own vhost (`CELERY_BROKER_URL=amqp://guest:guest@localhost:5672/bracelet_builder` in `.env`) — deliberately *not* the default `/` vhost, to stay isolated from other projects (e.g. Vadevia) that may share the same RabbitMQ instance.
- **Result backend**: Redis (`CELERY_RESULT_BACKEND`), unrelated to the broker choice — Celery's RabbitMQ result backend isn't well suited for this.
- **Queue**: `CELERY_TASK_DEFAULT_QUEUE = 'bracelet_builder'` is set explicitly in `settings.py` (not left at Celery's generic `"celery"` default), as defense in depth on top of the vhost isolation.
- **Task naming**: tasks are namespaced (e.g. `payment/tasks.py`'s `send_order_confirmation_email` is registered as `'bracelet_builder.send_order_confirmation_email'`), same reasoning — belt and suspenders against a vhost/queue ever being misconfigured to be shared later.
- Neither Redis nor RabbitMQ run in this dev sandbox by default — `.delay()` calls won't execute without a broker up. For testing task logic without infra, call the task's `.apply(args=[...])` (synchronous/eager) instead of `.delay()`.
- **Beat schedule**: `CELERY_BEAT_SCHEDULE` in `settings.py` runs `update_currency_rates` (`payment/tasks.py`) daily at 03:00 UTC. It fetches USD-relative rates from `open.er-api.com` (free, no API key) for `TARGET_CURRENCIES` (USD/MXN/EUR — MXN specifically for MercadoPago's settlement currency) and `get_or_create`s one `payment.CurrencyExchangeRate` row per currency per day — rows are appended, never overwritten in place, so the rate history stays reconstructable. Uses Celery's built-in file-based beat scheduler, not `django-celery-beat` (no extra dependency/app installed for it). This only fires if `celery -A bracelet_builder beat` is running alongside the worker — `CELERY_BEAT_SCHEDULE` being set does nothing on its own; forgetting the separate `beat` process is a silent no-op, not an error.

## Payment flow

Guest checkout, no login system — everything is keyed off the anonymous Django session, not a `user` FK.

1. `session['bracelet_build'] = {'base_id': <BraceletBase.id or None>, 'items': [<BraceletItem.id>, ...]}` — an ordered list, duplicates allowed, position = list index. Built up via `configurator.views.add_bracelet_item`/`remove_bracelet_item`/`select_bracelet_base`/`clear_bracelet` (all POST, HTMX-driven, re-rendering `partials/build_tray.html`). No base is assumed by default — `add_bracelet_item` requires `base_id` to be set first (the item carousel disables its Add buttons and shows a prompt until a size is chosen). `clear_bracelet` only empties `items`, leaving `base_id` untouched — clearing beads and switching size are treated as separate intents; it's gated behind htmx's `hx-confirm` (native `confirm()`) since it's destructive with no undo.
2. `configurator.views.checkout` (GET) shows the read-only tray + a guest info form (name/email/phone), which POSTs to `configurator.views.finalize_bracelet`.
3. Stock is checked twice, deliberately: `add_bracelet_item` checks cumulative demand at build time (existing occurrences in the session vs. `item.stock`, so the carousel can show "Only N left"/"Out of stock" live), and `finalize_bracelet` re-checks fresh from the DB with `collections.Counter` right before creating the `Order` — the second check is what actually catches another customer buying the same stock out from under this session between build time and checkout. On success `finalize_bracelet` creates `BraceletConfiguration(is_finalized=True)` + `BraceletConfigurationItem` rows (via `bulk_create`, position = `enumerate()` index), then `checkout.Order` + one `checkout.OrderItem`, clears the session, and redirects to `payment:choose_gateway`.
4. `payment.views.common.process_payment` is the **unified dispatch view** — reads the chosen gateway, sets `Order.gateway`, and redirects to the gateway-specific checkout view. It contains no gateway-specific charge logic itself; that lives in `payment/views/{stripe,paypal,mercadopago}.py`.
5. Stripe and PayPal are both **inline/JS-driven on our own pages** (Stripe.js Card Element, PayPal JS Buttons) — no navigation away from the site for the normal path. MercadoPago is the one gateway that's a true hosted-page redirect (`back_urls` configured for success/pending/failure).
6. All three gateways' success paths converge on `payment.services.finalize_paid_order(order, gateway, reference, amount, raw_response)` — the single place that marks the order paid, logs a `payment.PaymentTransaction`, decrements `BraceletItem.stock` (guarded against going negative, not reserved ahead of time — see the comment in `services.py` for the known oversell-race limitation), and enqueues `send_order_confirmation_email.delay()`. Don't duplicate this logic per-gateway.
7. `payment:payment_failed` is the cancel/decline landing page — reached from MercadoPago's `back_urls.failure` and from Stripe's `stripe_return` page (for the redirect-based-payment-method fallback; the normal in-page card flow shows errors inline instead). PayPal's cancel case (`onCancel` in `paypal_checkout.html`) shows an inline message rather than navigating away.
8. `checkout:order_confirmation` is the post-payment "thank you" page. `payment/tasks.py`'s `send_order_confirmation_email` (Celery) renders `templates/checkout/pdf/order_pdf.html` through WeasyPrint and emails it — same PDF attached to both — to the customer and to `settings.ADMINS` (admin body additionally includes customer name/email/phone). Retries specifically on `smtplib.SMTPException` with exponential backoff (`2 ** self.request.retries`), not a flat delay. `EMAIL_BACKEND` (see Configuration above) controls whether this actually sends mail or just logs to console.

`payment/tasks.py`'s other task, `update_currency_rates`, is unrelated to the checkout flow — see Background tasks (Celery) below.

`checkout.OrderItem.bracelet_configuration` is a plain nullable FK to `configurator.BraceletConfiguration` — deliberately not a generic `item_type`/`item_id` polymorphic scheme, since only one purchasable type exists today. See the docstring in `checkout/models.py` for the extension pattern (add another nullable FK + extend the `purchasable` property) if a second purchasable type is ever added.

## Architecture

- `bracelet_builder/` — project package: `settings.py`, `celery.py`, root `urls.py`, `asgi.py`/`wsgi.py`.
- `configurator/` — bracelet-building app. `urls.py` included at the project root (`app_name = "configurator"`, no prefix), URL names referenced as `configurator:<name>`.
- `checkout/` — `Order`/`OrderItem` models, order confirmation view. `urls.py` included under `/orders/` (`checkout:<name>`).
- `payment/` — gateway dispatch, `PaymentTransaction` and `CurrencyExchangeRate` models (both registered read-only in admin, no manual add — system-generated audit logs), `payment/views/` as a package (`common.py` for the dispatcher, one module per gateway), `payment/paypal_client.py` (raw `requests`-based PayPal Orders v2 API wrapper, not the `paypalrestsdk` package), `payment/services.py`, `payment/tasks.py`. `urls.py` included under `/payment/` (`payment:<name>`).
- `templates/` — project-level template directory (registered via `TEMPLATES[0]["DIRS"]`), not per-app `<app>/templates/`. `templates/base.html` is the shared shell all pages should extend; it loads HTMX and Swiper.js from CDN (no local/bundled copies, no npm build step) and wires HTMX's CSRF header via a global `getCookie()` helper other pages' inline scripts reuse. App-specific templates live under `templates/configurator/`, `templates/checkout/` (including `templates/checkout/pdf/order_pdf.html`, the WeasyPrint source), and `templates/payment/`. No per-page external CSS files anywhere — every template puts its styles inline in `{% block extra_head %}<style>`; when a partial (like `partials/build_tray.html`) is rendered standalone from multiple parent pages, its CSS is duplicated into each parent's `<style>` block rather than factored out, matching this convention.
- Static files: `STATICFILES_DIRS` points at a project-level `static/` directory; `STATIC_ROOT` (`staticfiles/`) is the `collectstatic` target — do not edit files there directly.
- Media: `MEDIA_ROOT` is `media/` at the repo root, served locally via `static()` in `bracelet_builder/urls.py` only when `DEBUG=True`. Item images uploaded through models' `ImageField`/`FileField` land here.
- HTMX out-of-band swaps are used once: `configurator.views.select_bracelet_base` returns both the re-rendered `size_selector.html` (primary `hx-target`) and `build_tray.html` with `hx-swap-oob="true"` (via an `oob` context flag on that template) concatenated in one response, so picking a size updates both widgets without collapsing/resetting the rest of the page.
- The `.bracelet-circle`/`.tray-item`/`.tray-item-remove` CSS (duplicated into `bracelet_builder.html` and `checkout.html` per the convention above) defines its sizing twice: a larger default (circle `480–630px`, base bead `72px`, scaling up through `.slot-2`/`.slot-3`/`.slot-4`) and a `@media (max-width: 600px)` block that reverts every one of those values back to a smaller set (circle `320–420px`, base bead `48px`). This isn't redundancy — `max-width: 100%` alone caps the circle's rendered box on narrow viewports but doesn't shrink the fixed-px `--radius`/bead-size values driving the `translate()` offsets that place beads on the ring, which would otherwise push beads outside the visibly-shrunk circle below ~600px. All values in both the default and the media-query set scale together by the same ratio (currently 1.5×) — if changing the enlargement factor, scale circle diameter, `--radius`, every `.tray-item`/`.slot-N` size+margin, `.tray-placeholder`, and `.tray-item-remove` size+offset together, in both `<style>` blocks, or the remove-button-overlap and bead-containment math silently drifts out of sync.
