# Day Night Pizza (Dunga Bunga) — Backend + Admin Panel

Full backend for Day Night Pizza, Main Bazar Thana Road, Dunga Bunga (phone 0304-7922262, open daily 1:30 PM – 1:30 AM): the storefront, a REST API and an admin
panel in one FastAPI app with a SQLite database (no external services needed).

## Run it

```bash
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
# or: ./start.sh
```

- Website: http://localhost:8000/
- Admin panel: http://localhost:8000/admin
- Default admin login: **admin / pizzaadmin** — change it in the panel (Settings tab) right away.

## What the admin panel controls

| Tab | Controls |
|---|---|
| Dashboard | Order count, revenue, pending orders, recent orders |
| Products | Add / edit / delete pizzas, prices per size, best-seller flag, show/hide, **image upload** |
| Deals | Add / edit / delete combo deals |
| Branches | Branch name, addresses, phone, opening hours (the site's live Open/Closed status is computed from these) |
| Orders | Every website order: customer, items, total, payment; status flow Pending → Confirmed → Preparing → On the way → Delivered / Cancelled; delete |
| Payments | Payment gateway: provider (Stripe / JazzCash / EasyPaisa), public key / merchant ID, secret key, currency, test mode, enable at checkout |
| Settings | Homepage texts (hero headline, hero text, Mega Deal banner), admin password change |

Everything is live: edits in the panel change the website on the next page load —
the storefront loads its menu, deals, branches and texts from `GET /api/bootstrap`,
and checkout posts real orders to `POST /api/orders`.

## Payment gateway — honest status

Keys are stored server-side (the secret is never sent to the browser). With a
provider enabled, checkout offers it next to Cash on Delivery and orders are
recorded with that method. Until **live** keys are saved and test mode is off,
gateway orders are recorded as `Gateway (demo — not charged)` — no real money
moves. Completing a fully live integration means pointing the provider's hosted
payment page / redirect at your merchant account with these keys; the settings,
order recording and status flow here are ready for that step.

## Files

- `app.py` — the whole backend (API + auth + SQLite schema + seed data)
- `pizza.db` — created automatically on first run, seeded with the real menu/deals/branches
- `static/` — website (`index.html`), admin panel (`admin.html`), product photos, fonts, icons
- `uploads/` — product images uploaded from the admin panel

## Deploying

Any Python host works (e.g. Render: `pip install -r requirements.txt` + start
command `uvicorn app:app --host 0.0.0.0 --port $PORT`). Note: on free tiers with
an ephemeral disk, `pizza.db` resets on redeploy — use a persistent disk or an
external database for production.
