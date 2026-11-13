from datetime import datetime
from hashlib import pbkdf2_hmac
from secrets import token_hex
import hmac

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import joinedload

from database import (
    init_database, SessionLocal, User, Category, Product, Order, OrderItem,
    Cart, Favorite, PromoCode, Setting
)

app = FastAPI(title="Зелёное яблоко")
app.add_middleware(SessionMiddleware, secret_key="change-this-secret-key-before-real-use")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def hash_password(password: str) -> str:
    salt = token_hex(16)
    digest = pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120000).hex()
    return f"{salt}${digest}"


def check_password(password: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$", 1)
        check = pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120000).hex()
        return hmac.compare_digest(check, digest)
    except ValueError:
        return False


def get_current_user(request: Request, db):
    user_id = request.session.get("user_id")
    return db.query(User).filter(User.id == user_id).first() if user_id else None


def setting(db, name, default):
    item = db.query(Setting).filter_by(name=name).first()
    return item.value if item else str(default)


def cart_rows(request, db, user):
    if user:
        rows = db.query(Cart).options(joinedload(Cart.product)).filter_by(user_id=user.id).all()
        return [(row.product, row.quantity) for row in rows if row.product]
    result = []
    for product_id, quantity in request.session.get("cart", {}).items():
        product = db.query(Product).filter_by(id=int(product_id), is_active=True).first()
        if product:
            result.append((product, int(quantity)))
    return result


def cart_count(rows):
    return sum(q for _, q in rows)


def merge_guest_cart(request: Request, db, user):
    """Переносит товары из гостевой корзины в корзину пользователя после входа."""
    guest_cart = request.session.get("cart", {})
    for product_id, quantity in guest_cart.items():
        product = db.query(Product).filter_by(id=int(product_id), is_active=True).first()
        if not product or product.stock <= 0:
            continue
        row = db.query(Cart).filter_by(user_id=user.id, product_id=product.id).first()
        if row:
            row.quantity = min(row.quantity + int(quantity), product.stock)
        else:
            db.add(Cart(user_id=user.id, product_id=product.id,
                        quantity=min(int(quantity), product.stock)))
    db.commit()
    request.session["cart"] = {}


def render(request, name, context=None, status_code=200):
    data = context or {}
    return templates.TemplateResponse(name, {"request": request, **data}, status_code=status_code)


@app.on_event("startup")
def startup():
    init_database()
    db = SessionLocal()
    try:
        if not db.query(User).filter_by(email="admin@greenapple.local").first():
            db.add(User(name="Администратор", email="admin@greenapple.local",
                        password_hash=hash_password("admin12345"), role="admin"))
            db.commit()
    finally:
        db.close()


@app.get("/", response_class=HTMLResponse)
def home(request: Request, q: str = "", category: int = 0):
    db = SessionLocal()
    try:
        user = get_current_user(request, db)
        query = db.query(Product).filter(Product.is_active == True)
        if q:
            query = query.filter(Product.name.ilike(f"%{q}%"))
        if category:
            query = query.filter(Product.category_id == category)
        products = query.order_by(Product.id).all()
        categories = db.query(Category).order_by(Category.id).all()
        rows = cart_rows(request, db, user)
        promos = db.query(PromoCode).filter_by(is_active=True).all()
        return render(request, "index.html", {"products": products, "categories": categories,
            "q": q, "selected_category": category, "user": user, "cart_count": cart_count(rows),
            "free_delivery": setting(db, "free_delivery_from", 1500),
            "promos": promos})
    finally:
        db.close()


@app.get("/category/{slug}", response_class=HTMLResponse)
def category_page(request: Request, slug: str, q: str = ""):
    """Показывает товары выбранной категории."""
    db = SessionLocal()
    try:
        category_item = db.query(Category).filter_by(slug=slug).first()
        if not category_item:
            return render(request, "index.html", {
                "products": [], "categories": db.query(Category).order_by(Category.id).all(),
                "q": q, "selected_category": 0, "category_name": "Категория не найдена",
                "user": get_current_user(request, db),
                "cart_count": cart_count(cart_rows(request, db, get_current_user(request, db))),
                "free_delivery": setting(db, "free_delivery_from", 1500),
                "promos": db.query(PromoCode).filter_by(is_active=True).all()
            }, status_code=404)
        user = get_current_user(request, db)
        query = db.query(Product).filter(Product.is_active == True, Product.category_id == category_item.id)
        if q:
            query = query.filter(Product.name.ilike(f"%{q}%"))
        products = query.order_by(Product.id).all()
        categories = db.query(Category).order_by(Category.id).all()
        rows = cart_rows(request, db, user)
        promos = db.query(PromoCode).filter_by(is_active=True).all()
        return render(request, "index.html", {
            "products": products, "categories": categories, "q": q,
            "selected_category": category_item.id, "category_name": category_item.name,
            "user": user, "cart_count": cart_count(rows),
            "free_delivery": setting(db, "free_delivery_from", 1500), "promos": promos
        })
    finally:
        db.close()


@app.get("/sales", response_class=HTMLResponse)
def sales_page(request: Request):
    """Отдельная страница акций и товаров со скидкой."""
    db = SessionLocal()
    try:
        user = get_current_user(request, db)
        rows = cart_rows(request, db, user)
        promos = db.query(PromoCode).filter_by(is_active=True).all()
        discounted_products = db.query(Product).filter(
            Product.is_active == True,
            Product.old_price.isnot(None),
            Product.old_price > Product.price
        ).order_by(Product.id).all()
        return render(request, "sales.html", {
            "user": user, "cart_count": cart_count(rows), "promos": promos,
            "products": discounted_products
        })
    finally:
        db.close()


@app.post("/cart/add/{product_id}")
def add_to_cart(request: Request, product_id: int):
    db = SessionLocal()
    try:
        product = db.query(Product).filter_by(id=product_id, is_active=True).first()
        if not product or product.stock <= 0:
            request.session["message"] = "Товар временно отсутствует"
            return RedirectResponse("/", status_code=303)
        user = get_current_user(request, db)
        if user:
            row = db.query(Cart).filter_by(user_id=user.id, product_id=product_id).first()
            if row:
                row.quantity = min(row.quantity + 1, product.stock)
            else:
                db.add(Cart(user_id=user.id, product_id=product_id, quantity=1))
            db.commit()
        else:
            cart = request.session.get("cart", {})
            key = str(product_id)
            cart[key] = min(int(cart.get(key, 0)) + 1, product.stock)
            request.session["cart"] = cart
        request.session["message"] = "Товар добавлен в корзину"
        return RedirectResponse("/", status_code=303)
    finally:
        db.close()


@app.get("/cart", response_class=HTMLResponse)
def show_cart(request: Request):
    db = SessionLocal()
    try:
        user = get_current_user(request, db)
        rows = cart_rows(request, db, user)
        subtotal = sum(float(p.price) * q for p, q in rows)
        promo_code = request.session.get("promo_code", "")
        promo_discount = 0.0
        promo_message = request.session.pop("promo_message", "")
        if promo_code:
            now = datetime.now()
            promo = db.query(PromoCode).filter_by(code=promo_code, is_active=True).first()
            if promo and (not promo.start_date or promo.start_date <= now) and (not promo.end_date or promo.end_date >= now):
                promo_discount = subtotal * promo.discount_percent / 100
                if not promo_message:
                    promo_message = f"Промокод {promo.code} применён. Скидка {promo.discount_percent}% — {promo_discount:.2f} ₽."
            else:
                request.session.pop("promo_code", None)
                promo_code = ""
                promo_message = "Промокод больше не действует."
        discounted_subtotal = max(0, subtotal - promo_discount)
        free_from = float(setting(db, "free_delivery_from", 1500))
        delivery = 0 if discounted_subtotal >= free_from else float(setting(db, "delivery_price", 199))
        return render(request, "cart.html", {"rows": rows, "subtotal": subtotal, "promo_discount": promo_discount,
            "promo_code": promo_code, "promo_message": promo_message, "delivery": delivery,
            "total": discounted_subtotal + delivery, "user": user, "cart_count": cart_count(rows),
            "message": request.session.pop("message", "")})
    finally:
        db.close()


@app.post("/cart/apply-promo")
def apply_promo(request: Request, promo_code: str = Form("")):
    db = SessionLocal()
    try:
        code = promo_code.strip().upper()
        if not code:
            request.session.pop("promo_code", None)
            request.session["promo_message"] = "Введите промокод."
            return RedirectResponse("/cart", status_code=303)
        promo = db.query(PromoCode).filter_by(code=code, is_active=True).first()
        now = datetime.now()
        if promo and (not promo.start_date or promo.start_date <= now) and (not promo.end_date or promo.end_date >= now):
            request.session["promo_code"] = promo.code
            rows = cart_rows(request, db, get_current_user(request, db))
            subtotal = sum(float(p.price) * q for p, q in rows)
            discount = subtotal * promo.discount_percent / 100
            request.session["promo_message"] = f"Промокод {promo.code} применён. Скидка {promo.discount_percent}% — {discount:.2f} ₽."
        else:
            request.session.pop("promo_code", None)
            request.session["promo_message"] = "Промокод не найден или уже не действует."
        return RedirectResponse("/cart", status_code=303)
    finally:
        db.close()


@app.post("/cart/update/{product_id}")
def update_cart(request: Request, product_id: int, quantity: int = Form(...)):
    db = SessionLocal()
    try:
        user = get_current_user(request, db)
        product = db.query(Product).filter_by(id=product_id).first()
        quantity = max(0, min(quantity, product.stock if product else 0))
        if user:
            row = db.query(Cart).filter_by(user_id=user.id, product_id=product_id).first()
            if row:
                if quantity == 0: db.delete(row)
                else: row.quantity = quantity
                db.commit()
        else:
            cart = request.session.get("cart", {})
            if quantity == 0: cart.pop(str(product_id), None)
            else: cart[str(product_id)] = quantity
            request.session["cart"] = cart
        return RedirectResponse("/cart", status_code=303)
    finally:
        db.close()


@app.post("/cart/remove/{product_id}")
def remove_cart(request: Request, product_id: int):
    return update_cart(request, product_id, quantity=0)


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return render(request, "auth.html", {"mode": "register", "error": ""})


@app.post("/register")
def register(request: Request, name: str = Form(...), email: str = Form(...), password: str = Form(...)):
    db = SessionLocal()
    try:
        email = email.strip().lower()
        if len(password) < 6:
            return render(request, "auth.html", {"mode":"register", "error":"Пароль должен быть не короче 6 символов"}, 400)
        if db.query(User).filter_by(email=email).first():
            return render(request, "auth.html", {"mode":"register", "error":"Эта почта уже зарегистрирована"}, 400)
        user = User(name=name.strip(), email=email, password_hash=hash_password(password))
        db.add(user); db.commit(); db.refresh(user)
        request.session["user_id"] = user.id
        merge_guest_cart(request, db, user)
        return RedirectResponse("/", status_code=303)
    finally:
        db.close()


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return render(request, "auth.html", {"mode": "login", "error": ""})


@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...)):
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(email=email.strip().lower()).first()
        if not user or not check_password(password, user.password_hash):
            return render(request, "auth.html", {"mode":"login", "error":"Неверная почта или пароль"}, 400)
        request.session["user_id"] = user.id
        merge_guest_cart(request, db, user)
        return RedirectResponse("/", status_code=303)
    finally:
        db.close()


@app.get("/logout")
def logout(request: Request):
    request.session.pop("user_id", None)
    return RedirectResponse("/", status_code=303)


@app.post("/checkout")
def checkout(request: Request, name: str = Form(...), phone: str = Form(...), address: str = Form(""),
             comment: str = Form(""), delivery_method: str = Form("delivery"), promo_code: str = Form("")):
    db = SessionLocal()
    try:
        user = get_current_user(request, db)
        if not user:
            request.session["message"] = "Для оформления заказа войдите или зарегистрируйтесь"
            return RedirectResponse("/login", status_code=303)
        rows = cart_rows(request, db, user)
        if not rows:
            return RedirectResponse("/cart", status_code=303)
        if not phone.strip():
            request.session["message"] = "Укажите номер телефона"
            return RedirectResponse("/cart", status_code=303)
        if delivery_method == "delivery" and not address.strip():
            request.session["message"] = "Укажите адрес доставки"
            return RedirectResponse("/cart", status_code=303)
        subtotal = sum(float(p.price) * q for p, q in rows)
        for product, quantity in rows:
            if quantity > product.stock:
                request.session["message"] = f"Недостаточно товара: {product.name}"
                return RedirectResponse("/cart", status_code=303)
        discount = 0
        promo_code = (promo_code or request.session.get("promo_code", "")).strip()
        if promo_code:
            promo = db.query(PromoCode).filter_by(code=promo_code.upper(), is_active=True).first()
            now = datetime.now()
            if promo and (not promo.start_date or promo.start_date <= now) and (not promo.end_date or promo.end_date >= now):
                discount = subtotal * promo.discount_percent / 100
            else:
                request.session["message"] = "Промокод не найден или уже не действует"
                return RedirectResponse("/cart", status_code=303)
        delivery = 0 if delivery_method == "pickup" or subtotal - discount >= float(setting(db,"free_delivery_from",1500)) else float(setting(db,"delivery_price",199))
        total = max(0, subtotal - discount) + delivery
        order = Order(user_id=user.id, total_price=total, phone=phone, address=address if delivery_method == "delivery" else "Самовывоз",
                      comment=comment, delivery_method=delivery_method, delivery_price=delivery, promo_discount=discount, status="новый")
        db.add(order); db.flush()
        for product, quantity in rows:
            db.add(OrderItem(order_id=order.id, product_id=product.id, quantity=quantity, price=product.price))
            product.stock -= quantity
        db.query(Cart).filter_by(user_id=user.id).delete()
        db.commit()
        request.session["cart"] = {}
        request.session.pop("promo_code", None)
        request.session.pop("promo_message", None)
        request.session["message"] = f"Заказ №{order.id} успешно оформлен"
        return RedirectResponse("/orders", status_code=303)
    finally:
        db.close()


@app.get("/orders", response_class=HTMLResponse)
def orders_page(request: Request):
    db = SessionLocal()
    try:
        user = get_current_user(request, db)
        if not user: return RedirectResponse("/login", status_code=303)
        orders = db.query(Order).options(joinedload(Order.items).joinedload(OrderItem.product)).filter_by(user_id=user.id).order_by(Order.created_at.desc()).all()
        return render(request, "orders.html", {"orders": orders, "user": user, "message": request.session.pop("message", "")})
    finally:
        db.close()


@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, message: str = ""):
    db = SessionLocal()
    try:
        user = get_current_user(request, db)
        if not user or user.role != "admin": return RedirectResponse("/login", status_code=303)
        products = db.query(Product).order_by(Product.id).all()
        orders = db.query(Order).order_by(Order.created_at.desc()).all()
        categories = db.query(Category).all()
        return render(request, "admin.html", {"user":user,"products":products,"orders":orders,"categories":categories,"message":message})
    finally: db.close()


@app.post("/admin/product")
def admin_add_product(request: Request, name: str = Form(...), category_id: int = Form(...), price: float = Form(...),
                      weight: str = Form(""), stock: int = Form(0), image: str = Form("")):
    db=SessionLocal()
    try:
        user=get_current_user(request,db)
        if not user or user.role!="admin": return RedirectResponse("/login",status_code=303)
        db.add(Product(name=name,category_id=category_id,price=price,weight=weight,stock=max(0,stock),image=image,is_active=True))
        db.commit(); return RedirectResponse("/admin?message=Товар+добавлен",status_code=303)
    finally: db.close()


@app.post("/admin/status/{order_id}")
def admin_status(request: Request, order_id: int, status: str = Form(...)):
    db=SessionLocal()
    try:
        user=get_current_user(request,db)
        if not user or user.role!="admin": return RedirectResponse("/login",status_code=303)
        allowed={"новый","принят","собирается","передан в доставку","выполнен","отменён"}
        order=db.query(Order).filter_by(id=order_id).first()
        if order and status in allowed: order.status=status; db.commit()
        return RedirectResponse("/admin",status_code=303)
    finally: db.close()


@app.get("/health")
def health():
    return {"status":"ok","app":"Зелёное яблоко"}
