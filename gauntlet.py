"""
THE GAUNTLET v2 - A hostile, mutating website that fights browser agents.

Level 0: Normal site (easy)
Level 1: Renamed buttons + popup
Level 2: Cookie banner + scrambled forms + decoys
Level 3: NIGHTMARE — trap pages, identical decoy buttons, misleading labels,
         popup overlay, the real submit is a tiny link, fake success page

Deployed on Vercel (stateless-friendly via ?level= query param).
"""

from flask import Flask, render_template_string, request, jsonify, redirect
import threading
import time
import hashlib
import json
import os

app = Flask(__name__)
app.secret_key = "gauntlet-2026"

MUTATION_LEVEL = 0
COMPLETION_LOG = {}
_log_lock = threading.Lock()

# ── Stateless level helper (Vercel-friendly) ─────────────────────────────────

def get_level():
    """Get mutation level from query param (stateless) or global (local dev)."""
    override = request.args.get("level") or request.form.get("level")
    if override is not None:
        try:
            return min(int(override), 3)
        except ValueError:
            pass
    return min(MUTATION_LEVEL, 3)

# ── Mutation Tables ───────────────────────────────────────────────────────────

BUTTONS = {
    0: {"add_cart": "Add to Cart", "checkout": "Proceed to Checkout", "place_order": "Place Order"},
    1: {"add_cart": "Buy Now", "checkout": "Continue", "place_order": "Complete Purchase"},
    2: {"add_cart": "Get This Item", "checkout": "Next Step", "place_order": "Submit Order"},
    3: {"add_cart": "I want this!", "checkout": "Keep Going", "place_order": "Finalize"},
}

DECOYS = {
    0: [],
    1: ["Continue Shopping"],
    2: ["Continue Shopping", "Save for Later"],
    3: ["Continue Shopping", "Save for Later", "Compare Items", "Add to Wishlist"],
}

FORM_FIELDS = {
    0: [
        {"name": "first_name", "label": "First Name", "placeholder": "John", "type": "text"},
        {"name": "last_name", "label": "Last Name", "placeholder": "Doe", "type": "text"},
        {"name": "email", "label": "Email", "placeholder": "john@example.com", "type": "email"},
        {"name": "address", "label": "Address", "placeholder": "123 Main St", "type": "text"},
        {"name": "city", "label": "City", "placeholder": "New York", "type": "text"},
        {"name": "state", "label": "State", "placeholder": "NY", "type": "text"},
        {"name": "zip_code", "label": "Zip Code", "placeholder": "10001", "type": "text"},
    ],
    1: [
        {"name": "first_name", "label": "Given Name", "placeholder": "Your first name", "type": "text"},
        {"name": "last_name", "label": "Family Name", "placeholder": "Your surname", "type": "text"},
        {"name": "email", "label": "Electronic Mail", "placeholder": "your@email.address", "type": "email"},
        {"name": "address", "label": "Street Address", "placeholder": "Street and number", "type": "text"},
        {"name": "city", "label": "Municipality", "placeholder": "City or town", "type": "text"},
        {"name": "state", "label": "Province/State", "placeholder": "State code", "type": "text"},
        {"name": "zip_code", "label": "Postal Code", "placeholder": "ZIP/Postal", "type": "text"},
    ],
    2: [
        {"name": "zip_code", "label": "", "placeholder": "Zip Code", "type": "text"},
        {"name": "city", "label": "", "placeholder": "City", "type": "text"},
        {"name": "state", "label": "", "placeholder": "State", "type": "text"},
        {"name": "address", "label": "", "placeholder": "Full Address", "type": "text"},
        {"name": "email", "label": "", "placeholder": "Email Address", "type": "email"},
        {"name": "last_name", "label": "", "placeholder": "Last Name", "type": "text"},
        {"name": "first_name", "label": "", "placeholder": "First Name", "type": "text"},
    ],
    3: [
        {"name": "email", "label": "Phone Number", "placeholder": "Required", "type": "text"},
        {"name": "first_name", "label": "Reference Code", "placeholder": "Enter code", "type": "text"},
        {"name": "address", "label": "Delivery Notes", "placeholder": "Special instructions", "type": "text"},
        {"name": "city", "label": "Promo Code", "placeholder": "Optional", "type": "text"},
        {"name": "zip_code", "label": "", "placeholder": "ID", "type": "text"},
        {"name": "state", "label": "", "placeholder": "Region", "type": "text"},
        {"name": "last_name", "label": "", "placeholder": "", "type": "hidden"},
    ],
}

POPUPS = {
    0: "",
    1: """<div id="popup-overlay" style="position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:999;display:flex;align-items:center;justify-content:center;">
        <div style="background:white;padding:30px;border-radius:12px;max-width:400px;text-align:center;">
            <h2 style="margin:0 0 10px">Newsletter</h2>
            <p>Sign up for 10% off!</p>
            <button onclick="document.getElementById('popup-overlay').remove()" style="background:#3b82f6;color:white;padding:10px 24px;border:none;border-radius:6px;cursor:pointer;margin-top:10px;">No thanks</button>
        </div>
    </div>""",
    2: """<div id="popup-cookies" style="position:fixed;bottom:0;left:0;right:0;background:#1f2937;color:white;padding:20px;z-index:998;display:flex;justify-content:space-between;align-items:center;">
        <span>We use cookies to enhance your experience.</span>
        <button onclick="document.getElementById('popup-cookies').remove()" style="background:#3b82f6;color:white;padding:8px 20px;border:none;border-radius:6px;cursor:pointer;">Accept All</button>
    </div>
    <div id="popup-overlay" style="position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:999;display:flex;align-items:center;justify-content:center;">
        <div style="background:white;padding:30px;border-radius:12px;max-width:400px;text-align:center;">
            <h2 style="margin:0 0 10px">Don't miss out!</h2>
            <p>Subscribe for exclusive deals!</p>
            <button onclick="document.getElementById('popup-overlay').remove()" style="background:#6b7280;color:white;padding:10px 24px;border:none;border-radius:6px;cursor:pointer;margin-top:10px;">Maybe Later</button>
        </div>
    </div>""",
    3: """<div id="popup-overlay" style="position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:999;display:flex;align-items:center;justify-content:center;">
        <div style="background:white;padding:30px;border-radius:12px;max-width:420px;text-align:center;">
            <h2 style="margin:0 0 10px;color:#ef4444;">WAIT! Before you go...</h2>
            <p>Get <b>50% OFF</b> your first order! Enter your email:</p>
            <input type="text" placeholder="your@email.com" style="width:90%;padding:10px;border:1px solid #d1d5db;border-radius:6px;margin:10px 0;">
            <br>
            <button style="background:#ef4444;color:white;padding:12px 32px;border:none;border-radius:6px;cursor:pointer;font-weight:700;font-size:16px;">GET MY DISCOUNT</button>
            <br>
            <button onclick="document.getElementById('popup-overlay').remove()" style="background:none;border:none;color:#9ca3af;cursor:pointer;margin-top:12px;font-size:13px;text-decoration:underline;">No thanks, I prefer paying full price</button>
        </div>
    </div>""",
}

STYLES = """
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; background: #f3f4f6; color: #111827; }
nav { background: white; padding: 12px 24px; border-bottom: 1px solid #e5e7eb; display: flex; justify-content: space-between; }
.logo { font-size: 20px; font-weight: 700; color: #2563eb; }
.container { max-width: 800px; margin: 32px auto; padding: 0 16px; }
.card { background: white; border-radius: 12px; padding: 32px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
.btn { padding: 12px 28px; border: none; border-radius: 8px; font-size: 16px; font-weight: 600; cursor: pointer; text-decoration: none; display: inline-block; }
.btn-primary { background: #2563eb; color: white; }
.btn-primary:hover { background: #1d4ed8; }
.btn-decoy { background: #f3f4f6; color: #6b7280; border: 1px solid #e5e7eb; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-size: 14px; text-decoration: none; display: inline-block; }
.btn-trap { background: #2563eb; color: white; padding: 12px 28px; border: none; border-radius: 8px; font-size: 16px; font-weight: 600; cursor: pointer; text-decoration: none; display: inline-block; }
h1 { margin: 0 0 16px; font-size: 28px; }
.price { font-size: 28px; font-weight: 700; color: #2563eb; margin: 16px 0; }
.product-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 32px; }
.product-img { background: linear-gradient(135deg, #dbeafe, #e9d5ff); border-radius: 12px; padding: 60px; text-align: center; font-size: 64px; }
.actions { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 24px; align-items: center; }
.field { margin-bottom: 16px; }
.field label { display: block; font-size: 14px; font-weight: 500; margin-bottom: 4px; color: #374151; }
.field input { width: 100%; padding: 10px 14px; border: 1px solid #d1d5db; border-radius: 8px; font-size: 16px; box-sizing: border-box; }
.field input:focus { outline: none; border-color: #2563eb; box-shadow: 0 0 0 3px rgba(37,99,235,0.1); }
.item-row { display: flex; justify-content: space-between; align-items: center; padding: 16px; border: 1px solid #e5e7eb; border-radius: 8px; margin-bottom: 16px; }
.total-row { display: flex; justify-content: space-between; font-size: 18px; font-weight: 700; padding-top: 16px; border-top: 2px solid #e5e7eb; }
.success-box { text-align: center; padding: 48px 32px; }
.success-icon { font-size: 64px; margin-bottom: 16px; }
.success-title { font-size: 32px; color: #16a34a; font-weight: 700; margin-bottom: 8px; }
.trap-link { color: #6b7280; font-size: 13px; text-decoration: underline; cursor: pointer; }
"""

def get_sid():
    return request.args.get("sid", request.form.get("sid", "unknown"))

def log_step(sid, step):
    with _log_lock:
        if sid not in COMPLETION_LOG:
            COMPLETION_LOG[sid] = {"steps": [], "success": False, "started": time.time()}
        if step not in COMPLETION_LOG[sid]["steps"]:
            COMPLETION_LOG[sid]["steps"].append(step)

def lq(sid, level):
    """Build level+sid query string for internal links."""
    return f"sid={sid}&level={level}"

def page(title, body, step, level=None):
    if level is None:
        level = get_level()
    popup_html = POPUPS.get(level, "")
    return render_template_string("""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>{{ title }} - TechNova</title>
<style>{{ styles }}</style></head>
<body>
<nav><span class="logo">TechNova Store</span><span style="color:#9ca3af;font-size:13px;">Level {{ level }}</span></nav>
<div class="container">{{ body | safe }}</div>
{{ popup | safe }}
</body></html>""", title=title, styles=STYLES, level=level, body=body, popup=popup_html)

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def product_page():
    sid = get_sid()
    level = get_level()
    log_step(sid, "product_page")
    btns = BUTTONS[level]
    decoys = DECOYS[level]
    q = lq(sid, level)

    decoy_html = "".join(f'<a href="#" class="btn-decoy">{d}</a>' for d in decoys)

    if level >= 3:
        body = f"""<div class="card">
    <div class="product-grid">
        <div class="product-img">&#129504;</div>
        <div>
            <h1>NeuroFlow X1</h1>
            <p style="color:#6b7280;">AI-Powered Focus Headband</p>
            <div class="price">$149.99</div>
            <p>Enhance your productivity with neural feedback technology.</p>
            <div class="actions" style="flex-direction:column;gap:8px;">
                <a href="/trap?{q}&from=product" class="btn-trap">Quick Buy - Express Checkout</a>
                <a href="/trap?{q}&from=product" class="btn-trap">Add to Cart & Checkout</a>
                <div style="display:flex;gap:8px;">
                    <a href="/trap?{q}&from=product" class="btn-trap">Reserve Item</a>
                    <a href="/trap?{q}&from=product" class="btn-trap">Buy with 1-Click</a>
                </div>
                {decoy_html}
                <a href="/cart?{q}" style="color:#6b7280;font-size:13px;text-decoration:underline;">{btns['add_cart']} &#8594;</a>
            </div>
        </div>
    </div>
</div>"""
    else:
        body = f"""<div class="card">
    <div class="product-grid">
        <div class="product-img">&#129504;</div>
        <div>
            <h1>NeuroFlow X1</h1>
            <p style="color:#6b7280;">AI-Powered Focus Headband</p>
            <div class="price">$149.99</div>
            <p>Enhance your productivity with neural feedback technology. 12-hour battery, Bluetooth 5.3, 30-day guarantee.</p>
            <div class="actions">
                {decoy_html}
                <a href="/cart?{q}" class="btn btn-primary">{btns['add_cart']}</a>
            </div>
        </div>
    </div>
</div>"""
    return page("NeuroFlow X1", body, 1, level)


@app.route("/trap")
def trap_page():
    """Trap page that looks like progress but is a dead end."""
    sid = get_sid()
    level = get_level()
    source = request.args.get("from", "unknown")
    q = lq(sid, level)

    body = f"""<div class="card" style="text-align:center;padding:48px;">
    <h1 style="color:#ef4444;">{"Oops! This item is temporarily unavailable." if source == "product" else "Something went wrong."}</h1>
    <p style="color:#6b7280;">{"We're experiencing high demand. Please try a different option." if source == "product" else "The page you requested could not be loaded."}</p>
    <div class="actions" style="justify-content:center;margin-top:24px;">
        <a href="/?{q}" class="btn btn-primary">Back to Product</a>
    </div>
</div>"""
    return page("Error", body, 0, level)


@app.route("/cart")
def cart_page():
    sid = get_sid()
    level = get_level()
    log_step(sid, "cart_page")
    btns = BUTTONS[level]
    decoys = DECOYS[level]
    q = lq(sid, level)

    decoy_html = "".join(f'<a href="#" class="btn-decoy">{d}</a>' for d in decoys)

    if level >= 3:
        body = f"""<div class="card">
    <h1>Your Cart</h1>
    <div class="item-row">
        <div><b>NeuroFlow X1</b><br><span style="color:#6b7280;font-size:14px;">AI-Powered Focus Headband - Qty: 1</span></div>
        <div style="font-weight:700;">$149.99</div>
    </div>
    <div class="total-row"><span>Total</span><span>$149.99</span></div>
    <div style="margin-top:16px;padding:12px;background:#fef3c7;border-radius:8px;font-size:14px;">
        <b>Limited offer!</b> Add a warranty for just $29.99
        <a href="/trap?{q}&from=cart" class="btn-trap" style="margin-left:12px;padding:6px 16px;font-size:13px;">Add Warranty & Checkout</a>
    </div>
    <div class="actions">
        <a href="/trap?{q}&from=cart" class="btn-trap">Express Checkout</a>
        <a href="/trap?{q}&from=cart" class="btn-trap">PayPal Checkout</a>
        {decoy_html}
        <a href="/checkout?{q}" style="color:#6b7280;font-size:13px;text-decoration:underline;">{btns['checkout']} &#8594;</a>
    </div>
</div>"""
    else:
        body = f"""<div class="card">
    <h1>Your Cart</h1>
    <div class="item-row">
        <div><b>NeuroFlow X1</b><br><span style="color:#6b7280;font-size:14px;">AI-Powered Focus Headband - Qty: 1</span></div>
        <div style="font-weight:700;">$149.99</div>
    </div>
    <div class="total-row"><span>Total</span><span>$149.99</span></div>
    <div class="actions">
        {decoy_html}
        <a href="/checkout?{q}" class="btn btn-primary">{btns['checkout']}</a>
    </div>
</div>"""
    return page("Your Cart", body, 2, level)


@app.route("/checkout")
def checkout_page():
    sid = get_sid()
    level = get_level()
    log_step(sid, "checkout_page")
    btns = BUTTONS[level]
    decoys = DECOYS[level]
    fields = FORM_FIELDS[level]
    q = lq(sid, level)

    fields_html = ""
    for f in fields:
        if f["type"] == "hidden":
            fields_html += f'<input type="hidden" name="{f["name"]}" value="N/A">'
        else:
            label_html = f'<label for="{f["name"]}">{f["label"]}</label>' if f["label"] else ""
            fields_html += f"""<div class="field">
                {label_html}
                <input type="text" name="{f['name']}" id="{f['name']}" placeholder="{f['placeholder']}">
            </div>"""

    decoy_html = "".join(f'<a href="#" class="btn-decoy">{d}</a>' for d in decoys)

    if level >= 3:
        body = f"""<div class="card">
    <h1>Shipping Information</h1>
    <p style="color:#6b7280;font-size:14px;">Fill in all fields to proceed.</p>
    <form action="/success" method="POST">
        <input type="hidden" name="sid" value="{sid}">
        <input type="hidden" name="level" value="{level}">
        {fields_html}
        <div class="actions">
            <a href="/fake-success?{q}" class="btn-trap">Place Order Now</a>
            <a href="/fake-success?{q}" class="btn-trap">Complete Purchase</a>
            {decoy_html}
            <button type="submit" style="background:none;border:none;color:#9ca3af;font-size:12px;cursor:pointer;text-decoration:underline;">{btns['place_order']}</button>
        </div>
    </form>
</div>"""
    else:
        body = f"""<div class="card">
    <h1>Shipping Information</h1>
    <form action="/success" method="POST">
        <input type="hidden" name="sid" value="{sid}">
        <input type="hidden" name="level" value="{level}">
        {fields_html}
        <div class="actions">
            {decoy_html}
            <button type="submit" class="btn btn-primary">{btns['place_order']}</button>
        </div>
    </form>
</div>"""
    return page("Checkout", body, 3, level)


@app.route("/fake-success", methods=["GET", "POST"])
def fake_success_page():
    """Looks like success but ORDER_CONFIRMED is NOT present."""
    sid = request.form.get("sid", request.args.get("sid", "unknown"))
    level = get_level()

    body = f"""<div class="card success-box">
    <div style="font-size:64px;">&#128230;</div>
    <h1 style="color:#f59e0b;">Processing Your Order...</h1>
    <p style="color:#6b7280;">Your payment is being verified. This may take a moment.</p>
    <p style="color:#6b7280;font-size:14px;">If this page doesn't update, <a href="/?{lq(sid, level)}">click here to retry</a>.</p>
    <div style="margin-top:24px;padding:16px;background:#fef3c7;border-radius:8px;">
        <p style="color:#92400e;">Status: PAYMENT_PENDING — Please wait...</p>
    </div>
</div>"""
    return page("Processing", body, 0, level)


@app.route("/success", methods=["GET", "POST"])
def success_page():
    sid = request.form.get("sid", request.args.get("sid", "unknown"))
    level = get_level()
    log_step(sid, "success")
    with _log_lock:
        if sid in COMPLETION_LOG:
            COMPLETION_LOG[sid]["success"] = True
            COMPLETION_LOG[sid]["completed"] = time.time()

    order_id = hashlib.md5(f"{sid}-{time.time()}".encode()).hexdigest()[:8].upper()

    body = f"""<div class="card success-box">
    <div class="success-icon">&#9989;</div>
    <div class="success-title">ORDER_CONFIRMED</div>
    <p style="color:#6b7280;">Order #{order_id}</p>
    <p style="color:#6b7280;">Your NeuroFlow X1 is on its way!</p>
    <div style="margin-top:24px;padding:16px;background:#f0fdf4;border-radius:8px;">
        <p style="color:#15803d;font-weight:600;">GAUNTLET_COMPLETE session={sid} mutation_level={level}</p>
    </div>
</div>"""
    return page("Order Confirmed", body, 4, level)


# ── Demo Dashboard ───────────────────────────────────────────────────────────

DEMO_HTML = """<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<title>Browser Evolution - Darwinian Prompt Breeding</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; line-height: 1.6; }
.hero { text-align: center; padding: 60px 24px 40px; background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); }
.hero h1 { font-size: 42px; font-weight: 800; background: linear-gradient(135deg, #60a5fa, #a78bfa); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 12px; }
.hero p { font-size: 18px; color: #94a3b8; max-width: 600px; margin: 0 auto; }
.badge { display: inline-block; background: #1e3a5f; color: #60a5fa; padding: 4px 12px; border-radius: 20px; font-size: 13px; font-weight: 600; margin-bottom: 16px; }
.container { max-width: 900px; margin: 0 auto; padding: 0 24px 60px; }
.section { margin-top: 48px; }
.section h2 { font-size: 24px; font-weight: 700; margin-bottom: 20px; color: #f1f5f9; }
.result-card { background: #1e293b; border-radius: 16px; padding: 32px; border: 1px solid #334155; }
.vs-row { display: grid; grid-template-columns: 1fr auto 1fr; gap: 24px; align-items: center; margin-bottom: 32px; }
.vs-col { text-align: center; padding: 24px; border-radius: 12px; }
.vs-col.fail { background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); }
.vs-col.pass { background: rgba(34, 197, 94, 0.1); border: 1px solid rgba(34, 197, 94, 0.3); }
.vs-label { font-size: 14px; color: #94a3b8; text-transform: uppercase; letter-spacing: 1px; }
.vs-score { font-size: 48px; font-weight: 800; margin: 8px 0; }
.vs-col.fail .vs-score { color: #ef4444; }
.vs-col.pass .vs-score { color: #22c55e; }
.vs-status { font-size: 20px; font-weight: 700; }
.vs-status.fail { color: #ef4444; }
.vs-status.pass { color: #22c55e; }
.vs-divider { font-size: 28px; font-weight: 800; color: #475569; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 12px 16px; text-align: left; border-bottom: 1px solid #334155; }
th { color: #94a3b8; font-weight: 600; font-size: 13px; text-transform: uppercase; letter-spacing: 1px; }
td { font-size: 15px; }
.delta-pos { color: #22c55e; font-weight: 700; }
.bar-container { display: flex; align-items: center; gap: 8px; }
.bar { height: 8px; border-radius: 4px; }
.bar-naive { background: #ef4444; }
.bar-evolved { background: #22c55e; }
.how-it-works { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.step-card { background: #1e293b; border-radius: 12px; padding: 20px; border: 1px solid #334155; }
.step-num { font-size: 32px; font-weight: 800; color: #60a5fa; }
.step-card h3 { font-size: 16px; margin: 8px 0 4px; }
.step-card p { font-size: 13px; color: #94a3b8; }
.cta-row { display: flex; gap: 16px; margin-top: 40px; justify-content: center; flex-wrap: wrap; }
.cta { display: inline-block; padding: 14px 32px; border-radius: 10px; font-size: 16px; font-weight: 700; text-decoration: none; transition: transform 0.1s; }
.cta:hover { transform: translateY(-2px); }
.cta-primary { background: linear-gradient(135deg, #2563eb, #7c3aed); color: white; }
.cta-secondary { background: #1e293b; color: #e2e8f0; border: 1px solid #334155; }
.gene-list { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 16px; }
.gene { background: #1e293b; border-radius: 8px; padding: 12px 16px; border: 1px solid #334155; }
.gene-name { font-size: 12px; color: #60a5fa; text-transform: uppercase; letter-spacing: 1px; font-weight: 600; }
.gene-desc { font-size: 13px; color: #cbd5e1; margin-top: 4px; }
.footer { text-align: center; padding: 32px 24px; color: #64748b; font-size: 14px; border-top: 1px solid #1e293b; }
.footer a { color: #60a5fa; text-decoration: none; }
@media (max-width: 640px) {
    .vs-row { grid-template-columns: 1fr; }
    .how-it-works { grid-template-columns: 1fr; }
    .gene-list { grid-template-columns: 1fr; }
    .hero h1 { font-size: 28px; }
}
</style>
</head>
<body>
<div class="hero">
    <div class="badge">Gemini/DeepMind Competition - BrowserUse Track</div>
    <h1>Browser Evolution</h1>
    <p>Darwinian natural selection breeds AI browser agents that survive hostile websites. Can evolution teach an AI to avoid traps?</p>
</div>

<div class="container">
    <div class="section">
        <h2>Head-to-Head: Naive vs Evolved</h2>
        <div class="result-card">
            <div class="vs-row">
                <div class="vs-col fail">
                    <div class="vs-label">Naive Prompt</div>
                    <div class="vs-score">47.5%</div>
                    <div class="vs-status fail">FAIL</div>
                    <div style="color:#94a3b8;font-size:13px;margin-top:8px;">30 actions | Got trapped</div>
                </div>
                <div class="vs-divider">VS</div>
                <div class="vs-col pass">
                    <div class="vs-label">Evolved Genome</div>
                    <div class="vs-score">94.5%</div>
                    <div class="vs-status pass">PASS</div>
                    <div style="color:#94a3b8;font-size:13px;margin-top:8px;">16 actions | ORDER_CONFIRMED</div>
                </div>
            </div>

            <table>
                <tr><th>Metric</th><th>Naive</th><th>Evolved</th><th>Delta</th></tr>
                <tr>
                    <td>Task Completion</td>
                    <td>50%</td>
                    <td>100%</td>
                    <td class="delta-pos">+50%</td>
                </tr>
                <tr>
                    <td>Efficiency</td>
                    <td>50%</td>
                    <td>80%</td>
                    <td class="delta-pos">+30%</td>
                </tr>
                <tr>
                    <td>Resilience (LLM Judge)</td>
                    <td>60%</td>
                    <td>100%</td>
                    <td class="delta-pos">+40%</td>
                </tr>
                <tr>
                    <td>Strategy (LLM Judge)</td>
                    <td>30%</td>
                    <td>90%</td>
                    <td class="delta-pos">+60%</td>
                </tr>
                <tr style="border-top:2px solid #475569;">
                    <td style="font-weight:700;">Composite Fitness</td>
                    <td style="font-weight:700;color:#ef4444;">47.5%</td>
                    <td style="font-weight:700;color:#22c55e;">94.5%</td>
                    <td class="delta-pos" style="font-size:18px;">+47%</td>
                </tr>
            </table>
        </div>
    </div>

    <div class="section">
        <h2>The Gauntlet - A Website That Fights Back</h2>
        <div class="result-card">
            <p style="margin-bottom:16px;">The Gauntlet is a hostile e-commerce site with 4 difficulty levels. At Level 3 (Nightmare):</p>
            <ul style="list-style:none;padding:0;">
                <li style="padding:6px 0;">&#128165; <b>4 trap buttons</b> styled identically to real buttons — all lead to dead-end error pages</li>
                <li style="padding:6px 0;">&#128270; <b>Real buttons are tiny grey links</b> — barely visible, easily missed</li>
                <li style="padding:6px 0;">&#128208; <b>Misleading form labels</b> — "Phone Number" field is actually for email</li>
                <li style="padding:6px 0;">&#128230; <b>Fake success page</b> — shows "PAYMENT_PENDING" instead of confirmation</li>
                <li style="padding:6px 0;">&#128172; <b>Popup overlays</b> — newsletter modals with tempting "GET MY DISCOUNT" button</li>
            </ul>
            <div class="cta-row" style="margin-top:24px;">
                <a href="/?level=3&sid=visitor" class="cta cta-primary">Try Nightmare Mode</a>
                <a href="/?level=0&sid=visitor" class="cta cta-secondary">Try Easy Mode</a>
            </div>
        </div>
    </div>

    <div class="section">
        <h2>How Evolution Works</h2>
        <div class="how-it-works">
            <div class="step-card">
                <div class="step-num">1</div>
                <h3>Spawn Population</h3>
                <p>Create random 6-gene browser agent genomes. Each gene controls a different skill.</p>
            </div>
            <div class="step-card">
                <div class="step-num">2</div>
                <h3>Evaluate & Judge</h3>
                <p>Run agents against The Gauntlet. Gemini 3 Flash judges their screenshots.</p>
            </div>
            <div class="step-card">
                <div class="step-num">3</div>
                <h3>Cull & Breed</h3>
                <p>Kill the weak. Survivors breed via crossover + mutation. LLM evolves genes.</p>
            </div>
        </div>
    </div>

    <div class="section">
        <h2>The Evolved Genome - 6 Genes</h2>
        <div class="gene-list">
            <div class="gene">
                <div class="gene-name">Navigation</div>
                <div class="gene-desc">Goal decomposition with alternative path scanning</div>
            </div>
            <div class="gene">
                <div class="gene-name">Element Selection</div>
                <div class="gene-desc">Semantic understanding + trap awareness: big buttons = traps</div>
            </div>
            <div class="gene">
                <div class="gene-name">Error Recovery</div>
                <div class="gene-desc">Adaptive strategy switching, trap page detection</div>
            </div>
            <div class="gene">
                <div class="gene-name">Distraction Handling</div>
                <div class="gene-desc">Immediate popup dismissal via dismiss links</div>
            </div>
            <div class="gene">
                <div class="gene-name">Form Interaction</div>
                <div class="gene-desc">Field name attributes over misleading labels</div>
            </div>
            <div class="gene">
                <div class="gene-name">Verification</div>
                <div class="gene-desc">Defensive checking, PAYMENT_PENDING detection</div>
            </div>
        </div>
    </div>

    <div class="section">
        <h2>Tech Stack</h2>
        <div class="result-card">
            <table>
                <tr><td style="color:#94a3b8;">Agent Brain</td><td>Gemini 2.5 Flash (via browser-use)</td></tr>
                <tr><td style="color:#94a3b8;">LLM Judges</td><td>Gemini 3 Flash Preview (multimodal, screenshot-grounded)</td></tr>
                <tr><td style="color:#94a3b8;">Evolution Engine</td><td>Custom Darwinian system (crossover + mutation + LLM gene evolution)</td></tr>
                <tr><td style="color:#94a3b8;">Observability</td><td>W&B Weave (full trace lineage)</td></tr>
                <tr><td style="color:#94a3b8;">Gauntlet</td><td>Flask hostile website (4 mutation levels)</td></tr>
                <tr><td style="color:#94a3b8;">Deployment</td><td>Vercel (gauntlet) + Railway (agent)</td></tr>
            </table>
        </div>
    </div>

    <div class="section">
        <h2>Live Demo — Run Agents Now</h2>
        <div class="result-card">
            <p style="margin-bottom:20px;">Launch real browser agents against the Nightmare Gauntlet (Level 3). Watch the naive agent get trapped while the evolved agent completes checkout.</p>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
                <div id="naive-panel" style="background:#0f172a;border-radius:12px;padding:20px;border:1px solid #334155;">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
                        <span style="font-weight:700;color:#ef4444;">Naive Agent</span>
                        <button onclick="runAgent('naive')" id="naive-btn" class="cta cta-secondary" style="padding:8px 20px;font-size:14px;">Run Naive</button>
                    </div>
                    <div id="naive-status" style="font-size:13px;color:#94a3b8;">Ready to launch</div>
                    <div id="naive-steps" style="margin-top:12px;font-size:13px;"></div>
                    <div id="naive-result" style="margin-top:12px;"></div>
                </div>
                <div id="evolved-panel" style="background:#0f172a;border-radius:12px;padding:20px;border:1px solid #334155;">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
                        <span style="font-weight:700;color:#22c55e;">Evolved Agent</span>
                        <button onclick="runAgent('evolved')" id="evolved-btn" class="cta cta-secondary" style="padding:8px 20px;font-size:14px;">Run Evolved</button>
                    </div>
                    <div id="evolved-status" style="font-size:13px;color:#94a3b8;">Ready to launch</div>
                    <div id="evolved-steps" style="margin-top:12px;font-size:13px;"></div>
                    <div id="evolved-result" style="margin-top:12px;"></div>
                </div>
            </div>
            <div style="text-align:center;margin-top:16px;">
                <button onclick="runAgent('naive');runAgent('evolved');" class="cta cta-primary" style="padding:12px 32px;">Race Both Agents</button>
            </div>
        </div>
    </div>

    <div class="cta-row">
        <a href="https://wandb.ai/carpediemhari-n-a/browser-evolution/weave" class="cta cta-primary" target="_blank">View W&B Weave Traces</a>
        <a href="/?level=3&sid=visitor" class="cta cta-secondary">Try The Gauntlet</a>
    </div>
</div>

<div class="footer">
    <p>Built for the Gemini/DeepMind BrowserUse Competition | <a href="https://wandb.ai/carpediemhari-n-a/browser-evolution/weave" target="_blank">W&B Weave</a></p>
</div>

<script>
const AGENT_API = 'https://browser-evolution-agent-production.up.railway.app';
const GAUNTLET_API = window.location.origin;

const NAIVE_PROMPT = `You are a browser automation assistant. Navigate to the given URL and complete the checkout process. Add the item to your cart, proceed to checkout, fill in the shipping form, and place the order.`;

const EVOLVED_PROMPT = `## NAVIGATION
Break the overall task into sub-goals. For a checkout flow: 1) Get the product into the cart, 2) Navigate to checkout, 3) Fill shipping info, 4) Complete the order. Scan for the most direct path. Look for alternative paths if needed.

## ELEMENT SELECTION
Use semantic understanding. Don't just match text — understand PURPOSE from context.
CRITICAL WARNING: This site is HOSTILE. The large, colorful blue buttons are ALL TRAPS that lead to error pages. The REAL action elements are tiny grey underlined text links, usually at the bottom. Look for small subtle links with arrows. Do NOT click any large blue button. If you see an error page, GO BACK and click the small grey text link instead.

## ERROR RECOVERY
If stuck for 2+ actions, switch strategies. If clicking buttons fails, try links. If you land on an error/pending page, GO BACK — you clicked a trap. Never repeat failing actions.

## DISTRACTION HANDLING
Immediately dismiss popups. Look for small grey dismiss links like "No thanks". Do NOT engage with popup content or click colorful CTA buttons in popups.

## FORM INTERACTION
WARNING: Labels may be DELIBERATELY WRONG. A field labeled "Phone Number" might be for email. Trust field name attribute and input type over visible label. Use: Alex Johnson, alex@example.com, 789 Elm Boulevard, Portland, OR, 97201. After filling, find the REAL submit — tiny grey underlined text, NOT the big blue buttons.

## VERIFICATION
Trust nothing. Task is complete ONLY with ORDER_CONFIRMED. If you see PAYMENT_PENDING, go back — that is a trap.`;

let timers = {};
let retries = {};

async function runAgent(type) {
    const btn = document.getElementById(type + '-btn');
    const status = document.getElementById(type + '-status');
    const steps = document.getElementById(type + '-steps');
    const result = document.getElementById(type + '-result');

    btn.disabled = true;
    btn.textContent = 'Running...';
    btn.style.opacity = '0.5';
    status.innerHTML = '<span style="color:#f59e0b;">Launching browser agent...</span>';
    steps.innerHTML = '';
    result.innerHTML = '';

    const prompt = type === 'naive' ? NAIVE_PROMPT : EVOLVED_PROMPT;
    const sid = 'live-' + type + '-' + Date.now();

    // Elapsed timer
    const startTime = Date.now();
    timers[type] = setInterval(() => {
        const elapsed = Math.round((Date.now() - startTime) / 1000);
        const dots = '.'.repeat((Math.floor(elapsed / 2) % 3) + 1);
        status.innerHTML = '<span style="color:#f59e0b;">Agent navigating browser' + dots + ' (' + elapsed + 's)</span>';
    }, 1000);

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 180000);

    try {
        const resp = await fetch(AGENT_API + '/run', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                prompt: prompt,
                gauntlet_url: GAUNTLET_API,
                level: 3,
                max_steps: 25,
                session_id: sid
            }),
            signal: controller.signal
        });
        clearTimeout(timeout);
        const data = await resp.json();

        clearInterval(timers[type]);

        // Show steps from agent response
        const agentSteps = data.steps_completed || [];
        steps.innerHTML = agentSteps.map(s => {
            const name = s === 'product_page' ? 'Product Page' : s === 'cart_page' ? 'Cart Page' : s === 'checkout_page' ? 'Checkout Page' : s === 'success' ? 'ORDER_CONFIRMED' : s;
            const color = s === 'success' ? '#22c55e' : '#60a5fa';
            return '<div style="padding:3px 0;color:' + color + ';">&#10003; ' + name + '</div>';
        }).join('');

        if (data.success) {
            status.innerHTML = '<span style="color:#22c55e;font-weight:700;font-size:16px;">PASS — ORDER_CONFIRMED</span>';
            result.innerHTML = '<div style="background:rgba(34,197,94,0.1);border:1px solid rgba(34,197,94,0.3);border-radius:8px;padding:12px;margin-top:8px;">' +
                '<div style="color:#22c55e;font-weight:700;">Checkout Complete</div>' +
                '<div style="color:#94a3b8;font-size:13px;">' + data.total_actions + ' actions | ' + data.duration + 's</div></div>';
        } else {
            status.innerHTML = '<span style="color:#ef4444;font-weight:700;font-size:16px;">FAIL — Did not complete checkout</span>';
            result.innerHTML = '<div style="background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);border-radius:8px;padding:12px;margin-top:8px;">' +
                '<div style="color:#ef4444;font-weight:700;">Checkout Failed</div>' +
                '<div style="color:#94a3b8;font-size:13px;">' + data.total_actions + ' actions | ' + data.duration + 's</div>' +
                '<div style="color:#94a3b8;font-size:12px;">Steps: ' + agentSteps.join(' → ') + '</div></div>';
        }

    } catch(e) {
        clearTimeout(timeout);
        clearInterval(timers[type]);
        if (e.name === 'AbortError') {
            status.innerHTML = '<span style="color:#ef4444;">Timed out (3 min limit)</span>';
        } else {
            retries[type] = (retries[type] || 0) + 1;
            if (retries[type] <= 2) {
                status.innerHTML = '<span style="color:#ef4444;">Connection error — retrying (' + retries[type] + '/2)...</span>';
                setTimeout(() => runAgent(type), 2000);
                return;
            } else {
                status.innerHTML = '<span style="color:#ef4444;">Agent API unavailable. Try again later.</span>';
                retries[type] = 0;
            }
        }
    }

    btn.disabled = false;
    btn.textContent = 'Run ' + type.charAt(0).toUpperCase() + type.slice(1);
    btn.style.opacity = '1';
}
</script>
</body></html>"""

@app.route("/demo")
def demo_page():
    return DEMO_HTML


# ── API ───────────────────────────────────────────────────────────────────────

@app.route("/api/mutation/<int:level>", methods=["POST"])
def set_mutation(level):
    global MUTATION_LEVEL
    MUTATION_LEVEL = level
    return jsonify({"mutation_level": MUTATION_LEVEL})

@app.route("/api/status/<session_id>")
def get_status(session_id):
    with _log_lock:
        data = COMPLETION_LOG.get(session_id, {"steps": [], "success": False})
    return jsonify(data)

@app.route("/api/reset", methods=["POST"])
def reset_log():
    global COMPLETION_LOG
    with _log_lock:
        COMPLETION_LOG = {}
    return jsonify({"status": "reset"})

@app.route("/api/stats")
def get_stats():
    with _log_lock:
        total = len(COMPLETION_LOG)
        successes = sum(1 for v in COMPLETION_LOG.values() if v["success"])
    return jsonify({"mutation_level": MUTATION_LEVEL, "total_sessions": total, "successes": successes})

def start_gauntlet(port=5000):
    thread = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False),
        daemon=True,
    )
    thread.start()
    time.sleep(1.5)
    return thread

if __name__ == "__main__":
    print("THE GAUNTLET v2 running on http://127.0.0.1:5000")
    print("Demo dashboard: http://127.0.0.1:5000/demo")
    app.run(host="127.0.0.1", port=5000, debug=True)
