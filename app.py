#!/usr/bin/env python3
"""
Day Night Pizza (Dunga Bunga) — backend + admin panel
FastAPI + SQLite. Serves the storefront, a REST API and an admin panel.

Run:  uvicorn app:app --host 0.0.0.0 --port 8000
Admin: http://localhost:8000/admin   (default login: admin / pizzaadmin — change it in the panel)
"""
import hashlib
import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "pizza.db"
STATIC = BASE / "static"
UPLOADS = BASE / "uploads"
UPLOADS.mkdir(exist_ok=True)

app = FastAPI(title="Day Night Pizza Backend", version="1.0.0")

# The storefront is hosted on Surge and calls this API cross-origin.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ---------------------------------------------------------------- DB helpers
@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS products(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, tagline TEXT DEFAULT '', image TEXT DEFAULT '',
            prices TEXT NOT NULL DEFAULT '[]', best_seller INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1, sort INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS deals(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            badge TEXT DEFAULT '', name TEXT NOT NULL, description TEXT DEFAULT '',
            price INTEGER NOT NULL DEFAULT 0, visual TEXT DEFAULT '[]',
            selects TEXT DEFAULT '[]', fixed TEXT DEFAULT '',
            active INTEGER DEFAULT 1, sort INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS branches(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, short_address TEXT DEFAULT '', address TEXT DEFAULT '',
            phone TEXT DEFAULT '', timing TEXT DEFAULT '',
            open_hour INTEGER DEFAULT 12, close_hour INTEGER DEFAULT 4,
            active INTEGER DEFAULT 1, sort INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT DEFAULT (datetime('now')),
            customer_name TEXT DEFAULT '', phone TEXT DEFAULT '', address TEXT DEFAULT '',
            branch TEXT DEFAULT '', mode TEXT DEFAULT 'Delivery',
            items TEXT NOT NULL DEFAULT '[]', total INTEGER DEFAULT 0,
            payment_method TEXT DEFAULT 'Cash on Delivery',
            payment_status TEXT DEFAULT 'Unpaid',
            status TEXT DEFAULT 'Pending', notes TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT DEFAULT '');
        """)
        if c.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
            seed(c)

def setting(c, key, default=""):
    row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else default

def set_setting(c, key, value):
    c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
              (key, str(value)))

def hash_pw(pw: str) -> str:
    return hashlib.sha256(("pw-salt:" + pw).encode()).hexdigest()

def seed(c):
    menu = [
        ("Afghani Pizza","Rich Afghani Flavor, Perfectly Baked.","Pizzaimages/Fajitapizza.png",[300,600,900],1),
        ("Stuffed Pizza","Loaded Inside, Delicious Outside.","Pizzaimages/SP.png",[350,600,1000],1),
        ("Crown Crust Pizza","The King of Crust.","Pizzaimages/Crown.png",[350,600,1000],1),
        ("Fajita Pizza","Classic chicken fajita with cheese and fresh toppings.","Pizzaimages/Fajitapizza.png",[230,420,680],1),
        ("Tikka Pizza","Flavorful chicken tikka with cheese and delicious toppings.","Pizzaimages/tikka11.png",[230,420,680],0),
        ("Cheese Lover Pizza","Rich and cheesy pizza made for cheese lovers.","Pizzaimages/cheze11.png",[230,420,680],0),
        ("Vege Lover Pizza","Fresh vegetables with cheese and delicious toppings.","Pizzaimages/vege11.png",[230,420,680],0),
        ("Supreme Pizza","Classic chicken fajita with cheese and fresh toppings.","Pizzaimages/fajita11.png",[230,420,680],0),
        ("Lazania Pizza","Our signature Day Night special pizza.","Pizzaimages/Lazania.png",[590,920],0),
        ("Malai Boti Pizza","Creamy Malai Boti chicken with cheese.","Pizzaimages/Malaiboti.webp",[350,600,900],0),
        ("Kabab Pizza","Juicy kabab pieces with cheese and toppings.","Pizzaimages/image1.webp",[300,600,900],0),
        ("BBQ Pizza","Smoky BBQ chicken with fresh toppings.","Pizzaimages/tikka.webp",[300,550,800],0),
        ("Turkey Pizza","Tender turkey with cheese and fresh toppings.","Pizzaimages/turkey-new.webp",[300,550,800],0),
        ("Creamy Pizza","Creamy pizza with cheese and delicious toppings.","Pizzaimages/CreamPizza.webp",[300,520,820],0),
        ("Peri Peri Pizza","Hot, Spicy, Delicious Peri Peri Pizza.","Pizzaimages/peri.png",[300,520,800],0),
        ("Kabab Crust","Delicious kabab crust with cheese and fresh toppings.","Pizzaimages/Kabab.webp",[800,1200],0),
    ]
    for i, (n, t, img, prices, best) in enumerate(menu):
        c.execute("INSERT INTO products(name,tagline,image,prices,best_seller,sort) VALUES(?,?,?,?,?,?)",
                  (n, t, img, json.dumps(prices), best, i))
    deals = [
        ("🔥 DEAL 1","Two Large Pizzas","Fixed combo — no flavour selection needed.",1360,
         ["Tikka Pizza","Fajita Pizza"], [], "Large Tikka Pizza + Large Fajita Pizza"),
        ("⭐ DEAL 2","Large + Medium","Choose the flavour of each pizza separately.",1100,
         [], [["Large Pizza Flavour",["Tikka","Fajita"]],["Medium Pizza Flavour",["Tikka","Fajita"]]], ""),
        ("🎁 DEAL 3","Large + Small","Choose the flavour of your Large and Small pizza separately.",910,
         [], [["Large Pizza Flavour",["Tikka","Fajita","Supreme","Cheese Lover","Veggie Lover"]],
              ["Small Pizza Flavour",["Tikka","Fajita","Supreme","Cheese Lover","Veggie Lover"]]], ""),
        ("👑 DEAL 4","Lazania + Large Pizza","Lazania Pizza is included. Choose Tikka or Fajita for the Large pizza.",1600,
         ["Lazania Pizza"], [["Large Pizza Flavour",["Tikka","Fajita"]]], "Lazania Pizza + "),
    ]
    for i, (b, n, d, p, v, s, f) in enumerate(deals):
        c.execute("INSERT INTO deals(badge,name,description,price,visual,selects,fixed,sort) VALUES(?,?,?,?,?,?,?,?)",
                  (b, n, d, p, json.dumps(v), json.dumps(s), f, i))
    branches = [
        ("Day Night Pizza","Main Bazar Thana Road, Dunga Bunga","Main Bazar Thana Road, Dunga Bunga, 62110, Pakistan","0304-7922262","1:30 PM to 1:30 AM",13,1),
    ]
    for i, (n, s, a, p, t, o, cl) in enumerate(branches):
        c.execute("INSERT INTO branches(name,short_address,address,phone,timing,open_hour,close_hour,sort) VALUES(?,?,?,?,?,?,?,?)",
                  (n, s, a, p, t, o, cl, i))
    defaults = {
        "store_name": "Day Night Pizza — Dunga Bunga",
        "hero_title": "Day ho ya night, <em>pizza</em> hamesha right.",
        "hero_lead": "Fresh, loaded pizzas in the heart of Dunga Bunga — dine in with family under the lights, or get it delivered hot to your door, from just <b>Rs. 230</b>.",
        "mega_title": "Day Night Mega Deal — Save 10% OFF",
        "mega_text": "Exclusive online offer — only at Day Night Pizza, Main Bazar Thana Road, Dunga Bunga. Dine-in, takeaway + delivery.",
        "admin_user": "admin",
        "admin_pass_hash": hash_pw("pizzaadmin"),
        "pay_provider": "none",          # none | stripe | jazzcash | easypaisa
        "pay_enabled": "0",
        "pay_test_mode": "1",
        "pay_public_key": "",            # Stripe publishable key / JazzCash merchant id / EasyPaisa store id
        "pay_secret_key": "",            # stored server-side only, never sent to the storefront
        "pay_currency": "PKR",
    }
    for k, v in defaults.items():
        set_setting(c, k, v)

init_db()

# ---------------------------------------------------------------- auth
TOKENS: dict[str, float] = {}

def require_admin(request: Request):
    auth = request.headers.get("authorization", "")
    token = auth.replace("Bearer ", "").strip()
    if not token or token not in TOKENS or TOKENS[token] < time.time():
        raise HTTPException(status_code=401, detail="Admin login required")
    return True

class LoginIn(BaseModel):
    username: str
    password: str

@app.post("/api/admin/login")
def admin_login(body: LoginIn):
    with db() as c:
        user = setting(c, "admin_user", "admin")
        ph = setting(c, "admin_pass_hash", "")
    if body.username == user and secrets.compare_digest(hash_pw(body.password), ph):
        token = secrets.token_urlsafe(32)
        TOKENS[token] = time.time() + 12 * 3600
        return {"token": token}
    raise HTTPException(status_code=401, detail="Wrong username or password")

@app.post("/api/admin/logout")
def admin_logout(request: Request, _=Depends(require_admin)):
    TOKENS.pop(request.headers.get("authorization", "").replace("Bearer ", "").strip(), None)
    return {"ok": True}

class PasswordIn(BaseModel):
    current: str
    new: str

@app.post("/api/admin/change-password")
def change_password(body: PasswordIn, _=Depends(require_admin)):
    with db() as c:
        if not secrets.compare_digest(hash_pw(body.current), setting(c, "admin_pass_hash", "")):
            raise HTTPException(status_code=400, detail="Current password is wrong")
        if len(body.new) < 6:
            raise HTTPException(status_code=400, detail="New password must be at least 6 characters")
        set_setting(c, "admin_pass_hash", hash_pw(body.new))
    return {"ok": True}

# ---------------------------------------------------------------- public API
def rows(c, sql, args=()):
    return [dict(r) for r in c.execute(sql, args).fetchall()]

def pub_product(r):
    return {"id": r["id"], "name": r["name"], "tagline": r["tagline"], "image": r["image"],
            "prices": json.loads(r["prices"]), "best_seller": bool(r["best_seller"])}

def pub_deal(r):
    return {"id": r["id"], "badge": r["badge"], "name": r["name"], "description": r["description"],
            "price": r["price"], "visual": json.loads(r["visual"]), "selects": json.loads(r["selects"]),
            "fixed": r["fixed"]}

def pub_branch(r):
    return {"id": r["id"], "name": r["name"], "short_address": r["short_address"], "address": r["address"],
            "phone": r["phone"], "timing": r["timing"], "open_hour": r["open_hour"], "close_hour": r["close_hour"]}

@app.get("/api/bootstrap")
def bootstrap():
    """Everything the storefront needs in one call."""
    with db() as c:
        products = [pub_product(r) for r in rows(c, "SELECT * FROM products WHERE active=1 ORDER BY sort,id")]
        deals = [pub_deal(r) for r in rows(c, "SELECT * FROM deals WHERE active=1 ORDER BY sort,id")]
        branches = [pub_branch(r) for r in rows(c, "SELECT * FROM branches WHERE active=1 ORDER BY sort,id")]
        site = {k: setting(c, k) for k in ("store_name", "hero_title", "hero_lead", "mega_title", "mega_text")}
        pay = {"enabled": setting(c, "pay_enabled") == "1",
               "provider": setting(c, "pay_provider", "none"),
               "public_key": setting(c, "pay_public_key"),
               "currency": setting(c, "pay_currency", "PKR")}
    return {"products": products, "deals": deals, "branches": branches, "site": site, "payment": pay}

@app.get("/api/products")
def list_products():
    with db() as c:
        return [pub_product(r) for r in rows(c, "SELECT * FROM products WHERE active=1 ORDER BY sort,id")]

class OrderIn(BaseModel):
    customer_name: str
    phone: str
    address: str = ""
    branch: str = ""
    mode: str = "Delivery"
    items: list
    total: int
    payment_method: str = "Cash on Delivery"
    notes: str = ""

@app.post("/api/orders")
def place_order(body: OrderIn):
    if not body.items:
        raise HTTPException(status_code=400, detail="Cart is empty")
    server_total = sum(int(i.get("price", 0)) * int(i.get("qty", 1)) for i in body.items)
    pay_status = "Unpaid" if body.payment_method == "Cash on Delivery" else "Gateway (demo — not charged)"
    with db() as c:
        cur = c.execute(
            "INSERT INTO orders(customer_name,phone,address,branch,mode,items,total,payment_method,payment_status,notes)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (body.customer_name, body.phone, body.address, body.branch, body.mode,
             json.dumps(body.items), server_total, body.payment_method, pay_status, body.notes))
        oid = cur.lastrowid
    return {"ok": True, "order_id": oid, "total": server_total}

# ---------------------------------------------------------------- admin API
@app.get("/api/admin/stats")
def stats(_=Depends(require_admin)):
    with db() as c:
        total_orders = c.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        revenue = c.execute("SELECT COALESCE(SUM(total),0) FROM orders WHERE status!='Cancelled'").fetchone()[0]
        pending = c.execute("SELECT COUNT(*) FROM orders WHERE status='Pending'").fetchone()[0]
        products = c.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        recent = rows(c, "SELECT * FROM orders ORDER BY id DESC LIMIT 5")
    for r in recent:
        r["items"] = json.loads(r["items"])
    return {"total_orders": total_orders, "revenue": revenue, "pending": pending,
            "products": products, "recent_orders": recent}

@app.get("/api/admin/products")
def admin_products(_=Depends(require_admin)):
    with db() as c:
        out = rows(c, "SELECT * FROM products ORDER BY sort,id")
    for r in out:
        r["prices"] = json.loads(r["prices"])
    return out

class ProductIn(BaseModel):
    name: str
    tagline: str = ""
    image: str = ""
    prices: list[int]
    best_seller: bool = False
    active: bool = True

@app.post("/api/admin/products")
def create_product(body: ProductIn, _=Depends(require_admin)):
    with db() as c:
        cur = c.execute("INSERT INTO products(name,tagline,image,prices,best_seller,active,sort)"
                        " VALUES(?,?,?,?,?,?,(SELECT COALESCE(MAX(sort),0)+1 FROM products))",
                        (body.name, body.tagline, body.image, json.dumps(body.prices),
                         int(body.best_seller), int(body.active)))
        return {"ok": True, "id": cur.lastrowid}

@app.put("/api/admin/products/{pid}")
def update_product(pid: int, body: ProductIn, _=Depends(require_admin)):
    with db() as c:
        c.execute("UPDATE products SET name=?,tagline=?,image=?,prices=?,best_seller=?,active=? WHERE id=?",
                  (body.name, body.tagline, body.image, json.dumps(body.prices),
                   int(body.best_seller), int(body.active), pid))
    return {"ok": True}

@app.delete("/api/admin/products/{pid}")
def delete_product(pid: int, _=Depends(require_admin)):
    with db() as c:
        c.execute("DELETE FROM products WHERE id=?", (pid,))
    return {"ok": True}

@app.get("/api/admin/deals")
def admin_deals(_=Depends(require_admin)):
    with db() as c:
        out = rows(c, "SELECT * FROM deals ORDER BY sort,id")
    for r in out:
        r["visual"] = json.loads(r["visual"]); r["selects"] = json.loads(r["selects"])
    return out

class DealIn(BaseModel):
    badge: str = ""
    name: str
    description: str = ""
    price: int
    visual: list = []
    selects: list = []
    fixed: str = ""
    active: bool = True

@app.post("/api/admin/deals")
def create_deal(body: DealIn, _=Depends(require_admin)):
    with db() as c:
        cur = c.execute("INSERT INTO deals(badge,name,description,price,visual,selects,fixed,active,sort)"
                        " VALUES(?,?,?,?,?,?,?,?,(SELECT COALESCE(MAX(sort),0)+1 FROM deals))",
                        (body.badge, body.name, body.description, body.price, json.dumps(body.visual),
                         json.dumps(body.selects), body.fixed, int(body.active)))
        return {"ok": True, "id": cur.lastrowid}

@app.put("/api/admin/deals/{did}")
def update_deal(did: int, body: DealIn, _=Depends(require_admin)):
    with db() as c:
        c.execute("UPDATE deals SET badge=?,name=?,description=?,price=?,visual=?,selects=?,fixed=?,active=? WHERE id=?",
                  (body.badge, body.name, body.description, body.price, json.dumps(body.visual),
                   json.dumps(body.selects), body.fixed, int(body.active), did))
    return {"ok": True}

@app.delete("/api/admin/deals/{did}")
def delete_deal(did: int, _=Depends(require_admin)):
    with db() as c:
        c.execute("DELETE FROM deals WHERE id=?", (did,))
    return {"ok": True}

@app.get("/api/admin/branches")
def admin_branches(_=Depends(require_admin)):
    with db() as c:
        return rows(c, "SELECT * FROM branches ORDER BY sort,id")

class BranchIn(BaseModel):
    name: str
    short_address: str = ""
    address: str = ""
    phone: str = ""
    timing: str = ""
    open_hour: int = 12
    close_hour: int = 4
    active: bool = True

@app.post("/api/admin/branches")
def create_branch(body: BranchIn, _=Depends(require_admin)):
    with db() as c:
        cur = c.execute("INSERT INTO branches(name,short_address,address,phone,timing,open_hour,close_hour,active,sort)"
                        " VALUES(?,?,?,?,?,?,?,?,(SELECT COALESCE(MAX(sort),0)+1 FROM branches))",
                        (body.name, body.short_address, body.address, body.phone, body.timing,
                         body.open_hour, body.close_hour, int(body.active)))
        return {"ok": True, "id": cur.lastrowid}

@app.put("/api/admin/branches/{bid}")
def update_branch(bid: int, body: BranchIn, _=Depends(require_admin)):
    with db() as c:
        c.execute("UPDATE branches SET name=?,short_address=?,address=?,phone=?,timing=?,open_hour=?,close_hour=?,active=? WHERE id=?",
                  (body.name, body.short_address, body.address, body.phone, body.timing,
                   body.open_hour, body.close_hour, int(body.active), bid))
    return {"ok": True}

@app.delete("/api/admin/branches/{bid}")
def delete_branch(bid: int, _=Depends(require_admin)):
    with db() as c:
        c.execute("DELETE FROM branches WHERE id=?", (bid,))
    return {"ok": True}

ORDER_STATUSES = ["Pending", "Confirmed", "Preparing", "On the way", "Delivered", "Cancelled"]

@app.get("/api/admin/orders")
def admin_orders(_=Depends(require_admin)):
    with db() as c:
        out = rows(c, "SELECT * FROM orders ORDER BY id DESC")
    for r in out:
        r["items"] = json.loads(r["items"])
    return out

class OrderStatusIn(BaseModel):
    status: str

@app.put("/api/admin/orders/{oid}/status")
def set_order_status(oid: int, body: OrderStatusIn, _=Depends(require_admin)):
    if body.status not in ORDER_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    with db() as c:
        c.execute("UPDATE orders SET status=? WHERE id=?", (body.status, oid))
    return {"ok": True}

@app.delete("/api/admin/orders/{oid}")
def delete_order(oid: int, _=Depends(require_admin)):
    with db() as c:
        c.execute("DELETE FROM orders WHERE id=?", (oid,))
    return {"ok": True}

@app.get("/api/admin/settings")
def admin_settings(_=Depends(require_admin)):
    keys = ("store_name", "hero_title", "hero_lead", "mega_title", "mega_text",
            "pay_provider", "pay_enabled", "pay_test_mode", "pay_public_key", "pay_currency")
    with db() as c:
        out = {k: setting(c, k) for k in keys}
        out["pay_secret_key_set"] = bool(setting(c, "pay_secret_key"))
    return out

class SettingsIn(BaseModel):
    values: dict[str, str]

@app.put("/api/admin/settings")
def update_settings(body: SettingsIn, _=Depends(require_admin)):
    allowed = {"store_name", "hero_title", "hero_lead", "mega_title", "mega_text",
               "pay_provider", "pay_enabled", "pay_test_mode", "pay_public_key",
               "pay_secret_key", "pay_currency"}
    with db() as c:
        for k, v in body.values.items():
            if k in allowed and v != "":
                set_setting(c, k, v)
    return {"ok": True}

@app.post("/api/admin/upload")
async def upload_image(file: UploadFile = File(...), _=Depends(require_admin)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        raise HTTPException(status_code=400, detail="Only image files (png/jpg/webp/gif)")
    name = f"{int(time.time())}-{secrets.token_hex(4)}{ext}"
    data = await file.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image larger than 8 MB")
    (UPLOADS / name).write_bytes(data)
    return {"ok": True, "path": f"uploads/{name}"}

@app.get("/api/health")
def health():
    return {"ok": True, "service": "daynight-pizza-backend"}

# ---------------------------------------------------------------- static files
@app.get("/admin")
def admin_page():
    return FileResponse(STATIC / "admin.html")

@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")

app.mount("/uploads", StaticFiles(directory=UPLOADS), name="uploads")
app.mount("/", StaticFiles(directory=STATIC), name="static")
