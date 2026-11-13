# База данных интернет-магазина «Зелёное яблоко»
# Для работы используется SQLite и SQLAlchemy.

from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# Файл базы данных появится рядом с этим файлом.
DATABASE_URL = "sqlite:///green_apple.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="user")  # user или admin
    created_at = Column(DateTime, default=datetime.now)


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    description = Column(Text)


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    category_id = Column(Integer, ForeignKey("categories.id"))
    name = Column(String(150), nullable=False)
    description = Column(Text)
    price = Column(Float, nullable=False)
    old_price = Column(Float)
    weight = Column(String(50))
    image = Column(String(255))
    stock = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    total_price = Column(Float, nullable=False)
    phone = Column(String(30), nullable=False)
    address = Column(Text)
    comment = Column(Text)
    delivery_method = Column(String(30), default="delivery")
    delivery_price = Column(Float, default=199)
    promo_discount = Column(Float, default=0)
    status = Column(String(30), default="новый")
    created_at = Column(DateTime, default=datetime.now)
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)  # Цена товара на момент покупки
    order = relationship("Order", back_populates="items")
    product = relationship("Product")


class Cart(Base):
    __tablename__ = "cart"
    __table_args__ = (UniqueConstraint("user_id", "product_id", name="unique_cart_product"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, default=1)
    product = relationship("Product")


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "product_id", name="unique_favorite_product"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)


class Promotion(Base):
    __tablename__ = "promotions"

    id = Column(Integer, primary_key=True)
    title = Column(String(150), nullable=False)
    description = Column(Text)
    image = Column(String(255))
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    is_active = Column(Boolean, default=True)


class PromoCode(Base):
    __tablename__ = "promo_codes"

    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False)
    discount_percent = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    start_date = Column(DateTime)
    end_date = Column(DateTime)


class Setting(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    value = Column(String(255), nullable=False)


def add_start_data():
    """Добавляет категории и товары, если база ещё пустая."""
    db = SessionLocal()
    try:
        if db.query(Category).count() == 0:
            categories = [
                Category(name="Фрукты и овощи", slug="frukty-i-ovoshchi", description="Свежие фрукты и овощи"),
                Category(name="Молочные продукты", slug="molochnye-produkty", description="Молоко и другие молочные продукты"),
                Category(name="Хлеб", slug="hleb", description="Хлеб и выпечка"),
                Category(name="Напитки", slug="napitki", description="Соки и напитки"),
            ]
            db.add_all(categories)
            db.commit()

        if db.query(Product).count() == 0:
            fruit = db.query(Category).filter_by(slug="frukty-i-ovoshchi").first()
            milk = db.query(Category).filter_by(slug="molochnye-produkty").first()
            bread = db.query(Category).filter_by(slug="hleb").first()
            drinks = db.query(Category).filter_by(slug="napitki").first()
            products = [
                Product(category_id=fruit.id, name="Свежие яблоки", description="Свежие яблоки", price=120, old_price=150, weight="1 кг", image="img/apple.jpeg", stock=30),
                Product(category_id=milk.id, name="Молоко 3.2%", description="Молоко 3.2%", price=90, weight="1 л", image="img/milk.webp", stock=25),
                Product(category_id=bread.id, name="Батон нарезной", description="Свежий батон", price=45, weight="0.4 кг", image="img/bread.png", stock=20),
                Product(category_id=fruit.id, name="Бананы", description="Свежие бананы", price=150, old_price=180, weight="1 кг", image="img/banana.webp", stock=25),
                Product(category_id=fruit.id, name="Помидоры Черри", description="Помидоры Черри", price=99, old_price=120, weight="0.5 кг", image="img/tomato.jpeg", stock=15),
                Product(category_id=drinks.id, name="Апельсиновый сок", description="Сок апельсиновый", price=130, old_price=150, weight="1 л", image="img/juice.jpeg", stock=18),
            ]
            db.add_all(products)
            db.commit()

        if db.query(Setting).count() == 0:
            db.add_all([
                Setting(name="free_delivery_from", value="1500"),
                Setting(name="delivery_price", value="199"),
                Setting(name="pickup_enabled", value="true"),
            ])
            db.commit()

        if db.query(PromoCode).count() == 0:
            db.add(PromoCode(code="SALE10", discount_percent=10, is_active=True))
            db.commit()
    finally:
        db.close()


def init_database():
    """Создаёт таблицы и добавляет начальные товары."""
    Base.metadata.create_all(bind=engine)
    add_start_data()


if __name__ == "__main__":
    init_database()
    print("База данных создана. Таблицы и тестовые товары добавлены.")
