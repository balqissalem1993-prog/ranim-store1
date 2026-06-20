"""
Ranim Store - Flask App
واجهة الزبون + الإدارة
"""
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from supabase import create_client
from datetime import datetime, timedelta
import uuid, qrcode, io, base64, os, urllib.parse

app = Flask(__name__)
app.secret_key = "ranim-secret-2026"

SUPABASE_URL = "https://xwwlffppepiwdiekqylr.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inh3d2xmZnBwZXBpd2RpZWtxeWxyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzk2NDcxMjksImV4cCI6MjA5NTIyMzEyOX0.bpWm7U4Z9JybPrEBPWmHhTRGZsq2CaaI7AVnuWKTZNg"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ══════════════════════════════════════
# دوال مساعدة
# ══════════════════════════════════════
def get_settings():
    try:
        rows = supabase.table("store_settings").select("*").execute().data
        if rows: return rows[0]
    except: pass
    return {"store_name":"RANIM","welcome_message":"مجوهرات فاخرة تليق بك",
            "whatsapp_number":"218910000000","logo_url":"","btn_text":"أضف للسلة",
            "color_primary":"#c9848a","color_accent":"#c9a96e",
            "color_bg":"#f9eced","color_text":"#4a2c2e",
            "maintenance_mode":False,"maintenance_msg":"","custom_banner":"","customer_url":""}

def save_settings(s):
    try:
        ex = supabase.table("store_settings").select("*").execute().data
        if ex: supabase.table("store_settings").update(s).eq("id", ex[0]["id"]).execute()
        else:  supabase.table("store_settings").insert(s).execute()
    except: pass

def load_users():
    try:
        rows = supabase.table("users").select("*").execute().data
        if rows:
            return {r["username"]: {"password": r["password"], "role": r.get("role","staff")} for r in rows}
    except: pass
    return {"Bashir": {"password": "B2026", "role": "admin"}, "Ahmed": {"password": "A2026", "role": "admin"}}

def save_user(username, password, role):
    try:
        ex = supabase.table("users").select("*").eq("username", username).execute().data
        if ex: supabase.table("users").update({"password": password, "role": role}).eq("username", username).execute()
        else:  supabase.table("users").insert({"username": username, "password": password, "role": role}).execute()
    except: pass

def add_log(action_type, amount, note, user_name):
    try:
        supabase.table("financial_logs").insert({
            "action_type": action_type, "amount": amount,
            "note": note, "user_name": user_name, "created_at": str(datetime.now())
        }).execute()
    except: pass

def calculate_capital(price_yuan, weight, pack_cost, bag_cost, dollar_rate, shipping_rate):
    return round((price_yuan*0.14)*dollar_rate + (weight*shipping_rate)*dollar_rate + pack_cost + bag_cost, 2)

def get_wallet(name):
    rows = supabase.table("wallets").select("*").eq("partner_name", name).execute().data
    return rows[0] if rows else None

def ensure_wallet(name):
    if not get_wallet(name):
        supabase.table("wallets").insert({"partner_name": name, "balance": 0}).execute()

def distribute_profit(profit):
    users = load_users()
    share = round(profit / len(users), 2) if users else 0
    for user in users:
        w = get_wallet(user)
        if w:
            supabase.table("wallets").update({"balance": w["balance"]+share}).eq("partner_name", user).execute()

def generate_qr(url):
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1a1118", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return "data:image/png;base64," + base64.b64encode(buf.read()).decode()

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_user"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated

# ══════════════════════════════════════
# واجهة الزبون
# ══════════════════════════════════════
@app.route("/")
def store():
    s = get_settings()
    products = []
    if not s.get("maintenance_mode"):
        products = supabase.table("products").select("*").execute().data
        products = [p for p in products if p.get("quantity",0)>0 and p.get("visible",True) is not False]
    selected_product = request.args.get("product", "")
    return render_template("store.html", s=s, products=products, selected_product=selected_product)

@app.route("/api/cart/order", methods=["POST"])
def place_order():
    data = request.json
    cart     = data.get("cart", {})
    customer = data.get("customer", {})
    coupon   = data.get("coupon_code", "")
    discount = 0

    # التحقق من الكوبون
    if coupon:
        try:
            coupons = supabase.table("coupons").select("*").eq("code", coupon.upper()).eq("active", True).execute().data
            if coupons:
                cp = coupons[0]
                total = sum(item["price"]*item["qty"] for item in cart.values())
                phone_target = cp.get("phone_target","")
                if (not phone_target) or phone_target == customer.get("phone",""):
                    if total >= cp.get("min_order",0):
                        discount = round(total*cp["value"]/100,2) if cp["type"]=="percent" else cp["value"]
        except: pass

    # حفظ الطلبات
    for pid, item in cart.items():
        try:
            supabase.table("orders").insert({
                "customer_name": customer.get("name"),
                "phone":         customer.get("phone"),
                "city":          customer.get("city"),
                "address":       customer.get("address"),
                "product_name":  item["name"],
                "quantity":      item["qty"],
                "total_price":   round(item["price"]*item["qty"],2),
                "notes":         customer.get("notes",""),
                "status":        "جديد",
                "managed_by":    "customer",
                "created_at":    str(datetime.now())
            }).execute()
        except: pass

    total_price = sum(item["price"]*item["qty"] for item in cart.values())
    final_price = max(0, round(total_price - discount, 2))

    items_summary = "%0A".join([f"• {v['name']} × {v['qty']} = {round(v['price']*v['qty'],2)} د.ل" for v in cart.values()])
    coupon_line = f"%0A🎁 كوبون: {coupon} (-{discount} د.ل)" if discount > 0 else ""
    s = get_settings()
    wa_msg = (f"🌸 طلب جديد - {s['store_name']}%0A{'─'*28}%0A"
              f"👤 {customer.get('name')}%0A📞 {customer.get('phone')}%0A"
              f"🏙️ {customer.get('city')}%0A📍 {customer.get('address')}%0A{'─'*28}%0A"
              f"🛒 المنتجات:%0A{items_summary}{coupon_line}%0A{'─'*28}%0A"
              f"💰 الإجمالي: {final_price} د.ل%0A📝 {customer.get('notes') or 'لا يوجد'}")
    wa_url = f"https://wa.me/{s['whatsapp_number']}?text={wa_msg}"

    return jsonify({"success": True, "wa_url": wa_url, "final_price": final_price})

@app.route("/api/coupon/check", methods=["POST"])
def check_coupon():
    data  = request.json
    code  = data.get("code","").upper()
    total = data.get("total", 0)
    phone = data.get("phone","")
    try:
        coupons = supabase.table("coupons").select("*").eq("code", code).eq("active", True).execute().data
        if not coupons:
            return jsonify({"valid": False, "msg": "كوبون غير صالح"})
        cp = coupons[0]
        phone_target = cp.get("phone_target","")
        if phone_target and phone_target != phone:
            return jsonify({"valid": False, "msg": "هذا الكوبون مخصص لزبون آخر"})
        if total < cp.get("min_order",0):
            return jsonify({"valid": False, "msg": f"الحد الأدنى للطلب {cp['min_order']} د.ل"})
        disc = round(total*cp["value"]/100,2) if cp["type"]=="percent" else cp["value"]
        return jsonify({"valid": True, "discount": disc, "msg": f"تم تطبيق خصم {disc} د.ل"})
    except Exception as e:
        return jsonify({"valid": False, "msg": "خطأ في الاتصال"})

@app.route("/api/review", methods=["POST"])
def submit_review():
    data = request.json
    try:
        supabase.table("reviews").insert({
            "rating": data.get("rating"), "review": data.get("review",""), "created_at": str(datetime.now())
        }).execute()
        return jsonify({"success": True})
    except:
        return jsonify({"success": False})

# ══════════════════════════════════════
# واجهة الإدارة
# ══════════════════════════════════════
@app.route("/admin")
def admin_login():
    if session.get("logged_user"):
        return redirect(url_for("admin_dashboard"))
    s = get_settings()
    return render_template("admin_login.html", s=s)

@app.route("/admin/login", methods=["POST"])
def do_login():
    username = request.form.get("username")
    password = request.form.get("password")
    users = load_users()
    if username in users:
        d = users[username]
        p = d["password"] if isinstance(d,dict) else d
        if p == password:
            session["logged_user"] = username
            session["role"] = d.get("role","staff") if isinstance(d,dict) else "admin"
            return redirect(url_for("admin_dashboard"))
    return render_template("admin_login.html", s=get_settings(), error="بيانات غير صحيحة")

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))

@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    try:
        products     = supabase.table("products").select("*").execute().data
        transactions = supabase.table("transactions").select("*").execute().data
        orders       = supabase.table("orders").select("*").execute().data
        total_profit = round(sum(t["profit"] for t in transactions), 2) if transactions else 0
        new_orders   = [o for o in orders if o.get("status")=="جديد"] if orders else []
        low_stock    = [p for p in products if p.get("quantity",0) < 5]
        last_sales   = list(reversed(transactions[-5:])) if transactions else []
        s = get_settings()
        return render_template("admin_dashboard.html",
            s=s, products=products, transactions=transactions,
            orders=orders, total_profit=total_profit,
            new_orders=new_orders, low_stock=low_stock, last_sales=last_sales,
            user=session.get("logged_user"), role=session.get("role"))
    except Exception as e:
        return render_template("admin_dashboard.html", error=str(e), s=get_settings(),
            user=session.get("logged_user"), role=session.get("role"),
            products=[], transactions=[], orders=[], total_profit=0,
            new_orders=[], low_stock=[], last_sales=[])

@app.route("/admin/products")
@admin_required
def admin_products():
    products = supabase.table("products").select("*").execute().data
    s = get_settings()
    customer_url = s.get("customer_url","")
    for p in products:
        if customer_url:
            p["qr"] = generate_qr(f"{customer_url}?product={urllib.parse.quote(p['name'])}")
    return render_template("admin_products.html", products=products, s=s,
        user=session.get("logged_user"), role=session.get("role"))

@app.route("/admin/products/add", methods=["POST"])
@admin_required
def add_product():
    f = request.form
    price_yuan    = float(f.get("price_yuan",0))
    weight        = float(f.get("weight",0))
    pack_cost     = float(f.get("pack_cost",0))
    bag_cost      = float(f.get("bag_cost",0))
    dollar_rate   = float(f.get("dollar_rate",7.1))
    shipping_rate = float(f.get("shipping_rate",12.5))
    qty           = int(f.get("qty",1))
    capital = calculate_capital(price_yuan, weight, pack_cost, bag_cost, dollar_rate, shipping_rate)
    image_url = ""
    if "image" in request.files and request.files["image"].filename:
        img_file = request.files["image"]
        fn = f"{uuid.uuid4()}.jpg"
        supabase.storage.from_("products").upload(fn, img_file.read())
        image_url = f"{SUPABASE_URL}/storage/v1/object/public/products/{fn}"
    p_name = f.get("name")
    existing = supabase.table("products").select("*").eq("name", p_name).execute().data
    if existing:
        supabase.table("products").update({"quantity": existing[0]["quantity"]+qty,
            "fixed_capital": capital, "selling_price": float(f.get("selling_price",0)),
            "image_url": image_url or existing[0].get("image_url",""),
            "max_order_qty": int(f.get("max_order_qty",qty))}).eq("name", p_name).execute()
    else:
        supabase.table("products").insert({"name": p_name, "quantity": qty,
            "fixed_capital": capital, "selling_price": float(f.get("selling_price",0)),
            "image_url": image_url, "max_order_qty": int(f.get("max_order_qty",qty))}).execute()
    purchase_source = f.get("purchase_source","cash")
    cap_row = supabase.table("capital_accounts").select("*").eq("account_type", purchase_source).execute().data
    if cap_row:
        supabase.table("capital_accounts").update({"balance": cap_row[0]["balance"]-(capital*qty)}).eq("account_type", purchase_source).execute()
    add_log("إضافة بضاعة", capital*qty, p_name, session.get("logged_user"))
    return redirect(url_for("admin_products"))

@app.route("/admin/products/update/<int:pid>", methods=["POST"])
@admin_required
def update_product(pid):
    f = request.form
    upd = {"quantity": int(f.get("quantity",0)), "selling_price": float(f.get("selling_price",0)),
           "max_order_qty": int(f.get("max_order_qty",1))}
    if "image" in request.files and request.files["image"].filename:
        img_file = request.files["image"]
        fn = f"{uuid.uuid4()}.jpg"
        supabase.storage.from_("products").upload(fn, img_file.read())
        upd["image_url"] = f"{SUPABASE_URL}/storage/v1/object/public/products/{fn}"
    supabase.table("products").update(upd).eq("id", pid).execute()
    return redirect(url_for("admin_products"))

@app.route("/admin/products/delete/<int:pid>", methods=["POST"])
@admin_required
def delete_product(pid):
    supabase.table("products").delete().eq("id", pid).execute()
    return redirect(url_for("admin_products"))

@app.route("/admin/products/visibility/<int:pid>", methods=["POST"])
@admin_required
def toggle_visibility(pid):
    product = supabase.table("products").select("*").eq("id", pid).execute().data
    if product:
        supabase.table("products").update({"visible": not product[0].get("visible",True)}).eq("id", pid).execute()
    return redirect(url_for("admin_products"))

@app.route("/admin/orders")
@admin_required
def admin_orders():
    orders = supabase.table("orders").select("*").execute().data or []
    products_all = supabase.table("products").select("*").execute().data or []
    sn = request.args.get("name","")
    sp = request.args.get("phone","")
    sc = request.args.get("city","")
    ss = request.args.get("status","الكل")
    if sn: orders=[o for o in orders if sn.lower() in o.get("customer_name","").lower()]
    if sp: orders=[o for o in orders if sp in o.get("phone","")]
    if sc: orders=[o for o in orders if sc.lower() in o.get("city","").lower()]
    if ss and ss!="الكل": orders=[o for o in orders if o.get("status")==ss]
    s = get_settings()
    return render_template("admin_orders.html", orders=orders, s=s, products=products_all,
        user=session.get("logged_user"), role=session.get("role"),
        filter_name=sn, filter_phone=sp, filter_city=sc, filter_status=ss)

@app.route("/admin/orders/update/<string:oid>", methods=["POST"])
@admin_required
def update_order_status(oid):
    new_status = request.form.get("status")
    order = supabase.table("orders").select("*").eq("id", oid).execute().data
    if order:
        o = order[0]
        old_status = o.get("status","جديد")
        supabase.table("orders").update({"status": new_status, "managed_by": session.get("logged_user")}).eq("id", oid).execute()
        if new_status=="تم التسليم" and old_status!="تم التسليم":
            pr = supabase.table("products").select("*").eq("name", o.get("product_name")).execute().data
            if pr:
                p = pr[0]
                total_sale  = o.get("total_price",0)
                total_cap   = p["fixed_capital"]*o.get("quantity",1)
                profit      = round(total_sale-total_cap, 2)
                supabase.table("products").update({"quantity": max(0,p["quantity"]-o.get("quantity",1))}).eq("id",p["id"]).execute()
                distribute_profit(profit)
                supabase.table("transactions").insert({"product_name":o.get("product_name"),"quantity":o.get("quantity"),
                    "total":total_sale,"capital":total_cap,"profit":profit,"payment_method":"cash",
                    "seller":session.get("logged_user"),"created_at":str(datetime.now())}).execute()
                add_log("إتمام طلب", total_sale, o.get("product_name"), session.get("logged_user"))
    return redirect(url_for("admin_orders"))

@app.route("/admin/orders/delete/<string:oid>", methods=["POST"])
@admin_required
def delete_order(oid):
    supabase.table("orders").delete().eq("id", oid).execute()
    return redirect(url_for("admin_orders"))

@app.route("/admin/orders/add", methods=["POST"])
@admin_required
def add_order():
    f = request.form
    products = supabase.table("products").select("*").execute().data
    o_product = f.get("product")
    o_qty     = int(f.get("qty",1))
    sel_prod  = next((p for p in products if p["name"]==o_product), None)
    o_total   = round(sel_prod["selling_price"]*o_qty,2) if sel_prod else 0
    supabase.table("orders").insert({
        "customer_name": f.get("name"), "phone": f.get("phone"), "city": f.get("city"),
        "address": f.get("address"), "product_name": o_product, "quantity": o_qty,
        "total_price": o_total, "notes": f.get("notes",""), "status": "جديد",
        "managed_by": session.get("logged_user"), "created_at": str(datetime.now())
    }).execute()
    return redirect(url_for("admin_orders"))

@app.route("/admin/sales")
@admin_required
def admin_sales():
    transactions = supabase.table("transactions").select("*").execute().data or []
    products     = supabase.table("products").select("*").execute().data or []
    s = get_settings()
    return render_template("admin_sales.html", transactions=transactions, products=products, s=s,
        user=session.get("logged_user"), role=session.get("role"))

@app.route("/admin/sales/add", methods=["POST"])
@admin_required
def add_sale():
    f = request.form
    product_name   = f.get("product")
    qty_sell       = int(f.get("qty",1))
    payment_method = f.get("payment","cash")
    products = supabase.table("products").select("*").execute().data
    product  = next((p for p in products if p["name"]==product_name), None)
    if product and qty_sell <= product["quantity"]:
        total_sale    = product["selling_price"]*qty_sell
        total_capital = product["fixed_capital"]*qty_sell
        profit        = round(total_sale-total_capital, 2)
        supabase.table("products").update({"quantity": product["quantity"]-qty_sell}).eq("id",product["id"]).execute()
        distribute_profit(profit)
        cap_row = supabase.table("capital_accounts").select("*").eq("account_type",payment_method).execute().data
        if cap_row:
            supabase.table("capital_accounts").update({"balance":cap_row[0]["balance"]+total_sale}).eq("account_type",payment_method).execute()
        supabase.table("transactions").insert({"product_name":product_name,"quantity":qty_sell,
            "total":total_sale,"capital":total_capital,"profit":profit,
            "payment_method":payment_method,"seller":session.get("logged_user"),"created_at":str(datetime.now())}).execute()
        add_log("بيع", total_sale, f"{product_name} x{qty_sell}", session.get("logged_user"))
    return redirect(url_for("admin_sales"))

@app.route("/admin/finance")
@admin_required
def admin_finance():
    wallets   = supabase.table("wallets").select("*").execute().data or []
    capitals  = supabase.table("capital_accounts").select("*").execute().data or []
    logs      = supabase.table("financial_logs").select("*").execute().data or []
    users     = load_users()
    s = get_settings()
    seen, unique_wallets = set(), []
    for w in wallets:
        if w["partner_name"] not in seen:
            seen.add(w["partner_name"]); unique_wallets.append(w)
    return render_template("admin_finance.html", wallets=unique_wallets, capitals=capitals,
        logs=list(reversed(logs)), users=users, s=s,
        user=session.get("logged_user"), role=session.get("role"))

@app.route("/admin/finance/wallet", methods=["POST"])
@admin_required
def wallet_action():
    f      = request.form
    action = f.get("action")
    user   = f.get("user")
    amount = float(f.get("amount",0))
    note   = f.get("note","")
    w = get_wallet(user)
    if action == "withdraw":
        if w and amount <= w["balance"]:
            supabase.table("wallets").update({"balance": w["balance"]-amount}).eq("partner_name",user).execute()
            add_log("سحب من المحفظة", amount, note or user, session.get("logged_user"))
    else:
        if w: supabase.table("wallets").update({"balance": w["balance"]+amount}).eq("partner_name",user).execute()
        else: supabase.table("wallets").insert({"partner_name":user,"balance":amount}).execute()
        add_log("إضافة للمحفظة", amount, note or user, session.get("logged_user"))
    return redirect(url_for("admin_finance"))

@app.route("/admin/finance/capital", methods=["POST"])
@admin_required
def capital_action():
    f            = request.form
    action       = f.get("action")
    account_type = f.get("account_type")
    amount       = float(f.get("amount",0))
    ex = supabase.table("capital_accounts").select("*").eq("account_type",account_type).execute().data
    if ex:
        bal     = ex[0]["balance"]
        new_bal = bal+amount if action=="add" else bal-amount
        if action=="withdraw" and amount>bal: return redirect(url_for("admin_finance"))
        supabase.table("capital_accounts").update({"balance":new_bal}).eq("account_type",account_type).execute()
        add_log("إضافة" if action=="add" else "سحب", amount, account_type, session.get("logged_user"))
    return redirect(url_for("admin_finance"))

@app.route("/admin/settings", methods=["GET","POST"])
@admin_required
def admin_settings():
    if session.get("role") != "admin":
        return redirect(url_for("admin_dashboard"))
    s = get_settings()
    users = load_users()
    coupons = []
    try: coupons = supabase.table("coupons").select("*").execute().data or []
    except: pass
    products_all = supabase.table("products").select("*").execute().data or []
    if request.method == "POST":
        action = request.form.get("action")
        if action == "save_info":
            s.update({"store_name": request.form.get("store_name"),
                "welcome_message": request.form.get("welcome_message"),
                "whatsapp_number": request.form.get("whatsapp_number"),
                "btn_text": request.form.get("btn_text"),
                "customer_url": request.form.get("customer_url")})
            if "logo" in request.files and request.files["logo"].filename:
                logo_file = request.files["logo"]
                fn = f"logo_{uuid.uuid4()}.png"
                supabase.storage.from_("products").upload(fn, logo_file.read())
                s["logo_url"] = f"{SUPABASE_URL}/storage/v1/object/public/products/{fn}"
            save_settings(s)
        elif action == "save_colors":
            s.update({"color_primary": request.form.get("color_primary"),
                "color_accent": request.form.get("color_accent"),
                "color_bg": request.form.get("color_bg"),
                "color_text": request.form.get("color_text")})
            save_settings(s)
        elif action == "save_advanced":
            s.update({"maintenance_mode": request.form.get("maintenance_mode")=="on",
                "maintenance_msg": request.form.get("maintenance_msg"),
                "custom_banner": request.form.get("custom_banner")})
            save_settings(s)
        elif action == "add_user":
            nu = request.form.get("username")
            np = request.form.get("password")
            nr = request.form.get("role","staff")
            save_user(nu, np, nr)
            ensure_wallet(nu)
        elif action == "change_password":
            cu = request.form.get("change_user")
            np = request.form.get("new_password")
            d  = users.get(cu, {})
            r  = d.get("role","staff") if isinstance(d,dict) else "admin"
            save_user(cu, np, r)
        elif action == "toggle_product_visibility":
            pid = request.form.get("product_id")
            product = supabase.table("products").select("*").eq("id", pid).execute().data
            if product:
                supabase.table("products").update({"visible": not product[0].get("visible",True)}).eq("id", pid).execute()
        elif action == "add_coupon":
            c_type = "percent" if "%" in request.form.get("coupon_type","") else "fixed"
            try:
                supabase.table("coupons").insert({
                    "code": request.form.get("coupon_code","").upper(),
                    "type": c_type, "value": float(request.form.get("coupon_value",0)),
                    "min_order": float(request.form.get("coupon_min",0)),
                    "active": True,
                    "phone_target": request.form.get("phone_target",""),
                    "created_at": str(datetime.now())
                }).execute()
            except: pass
        return redirect(url_for("admin_settings"))
    return render_template("admin_settings.html", s=s, users=users, coupons=coupons, products=products_all,
        user=session.get("logged_user"), role=session.get("role"))

@app.route("/admin/settings/coupon_toggle/<string:cid>", methods=["POST"])
@admin_required
def toggle_coupon(cid):
    cp = supabase.table("coupons").select("*").eq("id",cid).execute().data
    if cp:
        supabase.table("coupons").update({"active": not cp[0].get("active")}).eq("id",cid).execute()
    return redirect(url_for("admin_settings"))

@app.route("/admin/settings/coupon_delete/<string:cid>", methods=["POST"])
@admin_required
def delete_coupon(cid):
    supabase.table("coupons").delete().eq("id",cid).execute()
    return redirect(url_for("admin_settings"))

@app.route("/admin/reports")
@admin_required
def admin_reports():
    transactions = supabase.table("transactions").select("*").execute().data or []
    orders       = supabase.table("orders").select("*").execute().data or []
    products     = supabase.table("products").select("*").execute().data or []
    reviews      = []
    try: reviews = supabase.table("reviews").select("*").execute().data or []
    except: pass
    s = get_settings()

    # إشعارات
    notifs = []
    new_orders_list = [o for o in orders if o.get("status")=="جديد"]
    if new_orders_list:
        notifs.append({"icon":"🆕","msg":f"لديك {len(new_orders_list)} طلب جديد","color":"#6366f1"})
    for p in [p for p in products if p.get("quantity",0) < 5]:
        notifs.append({"icon":"⚠️","msg":f"مخزون منخفض: {p['name']} — {p['quantity']} قطعة","color":"#f59e0b"})
    today = datetime.now().date()
    today_sales = [t for t in transactions if str(today) in str(t.get("created_at",""))]
    if today_sales:
        notifs.append({"icon":"📈","msg":f"أرباح اليوم: {round(sum(t['profit'] for t in today_sales),2)} د.ل","color":"#10b981"})

    # هدف الشهر
    goal = float(request.args.get("goal", 5000))
    this_month   = datetime.now().strftime("%Y-%m")
    month_profit = sum(t["profit"] for t in transactions if this_month in str(t.get("created_at","")))
    pct = min(int((month_profit / goal) * 100), 100) if goal > 0 else 0

    # متوسط التقييم
    avg_rating = round(sum(r["rating"] for r in reviews)/len(reviews), 1) if reviews else 0

    return render_template("admin_reports.html", transactions=transactions,
        orders=orders, products=products, reviews=list(reversed(reviews)), s=s,
        notifs=notifs, goal=goal, month_profit=round(month_profit,2), pct=pct,
        avg_rating=avg_rating,
        user=session.get("logged_user"), role=session.get("role"))

@app.route("/admin/export/<string:table_name>")
@admin_required
def export_data(table_name):
    import pandas as pd
    tm = {"المنتجات":"products","المبيعات":"transactions","الطلبات":"orders","السجل المالي":"financial_logs"}
    tn = tm.get(table_name, table_name)
    data = supabase.table(tn).select("*").execute().data
    if not data:
        return redirect(url_for("admin_reports"))
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(data).to_excel(writer, index=False, sheet_name=table_name[:30])
    output.seek(0)
    from flask import send_file
    return send_file(output, as_attachment=True,
        download_name=f"{table_name}_{datetime.now().date()}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route("/admin/backup")
@admin_required
def backup_data():
    import pandas as pd
    tables = {"المنتجات":"products","المبيعات":"transactions","الطلبات":"orders",
              "السجل المالي":"financial_logs","المحافظ":"wallets","رأس المال":"capital_accounts"}
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sn,tn in tables.items():
            try:
                data = supabase.table(tn).select("*").execute().data
                if data: pd.DataFrame(data).to_excel(writer, index=False, sheet_name=sn)
            except: pass
    output.seek(0)
    from flask import send_file
    return send_file(output, as_attachment=True,
        download_name=f"backup_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route("/admin/search")
@admin_required
def admin_search():
    section = request.args.get("section","المنتجات")
    query   = request.args.get("query","")
    results = []
    if query:
        if section=="المنتجات":
            results=[p for p in supabase.table("products").select("*").execute().data if query.lower() in p["name"].lower()]
        elif section=="المبيعات":
            results=[t for t in supabase.table("transactions").select("*").execute().data if query.lower() in t["product_name"].lower() or query.lower() in t.get("seller","").lower()]
        elif section=="الطلبات":
            results=[o for o in supabase.table("orders").select("*").execute().data if query.lower() in o.get("customer_name","").lower() or query in o.get("phone","") or query.lower() in o.get("city","").lower()]
        elif section=="السجل المالي":
            results=[l for l in supabase.table("financial_logs").select("*").execute().data if query.lower() in l.get("action_type","").lower() or query.lower() in l.get("note","").lower()]
    s = get_settings()
    return render_template("admin_search.html", results=results, section=section, query=query, s=s,
        user=session.get("logged_user"), role=session.get("role"))

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT",5000)))
