from datetime import datetime
from typing import Optional
from sqlalchemy import BigInteger, String, Float, Boolean, DateTime, Integer, Text, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    """Модель пользователя"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # Telegram ID
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Статус подписки
    is_subscribed: Mapped[bool] = mapped_column(Boolean, default=False)
    subscription_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Даты
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_activity: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Связи
    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    payments: Mapped[list["Payment"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.id} (@{self.username})>"


class Subscription(Base):
    """История подписок пользователя"""
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    
    # Параметры подписки
    duration_months: Mapped[int] = mapped_column(Integer)  # 1, 3, 6, 12
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    
    # Источник активации
    activated_by: Mapped[str] = mapped_column(String(20))  # 'payment', 'promo', 'manual'
    promocode: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Статус
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Связи
    user: Mapped["User"] = relationship(back_populates="subscriptions")

    def __repr__(self):
        return f"<Subscription user={self.user_id} expires={self.expires_at}>"


class Promocode(Base):
    """Промокоды для скидок и подарков"""
    __tablename__ = "promocodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    
    # Тип промокода
    discount_type: Mapped[str] = mapped_column(String(20))  # 'percent', 'fixed', 'free'
    discount_value: Mapped[float] = mapped_column(Float)  # процент или сумма скидки
    
    # Параметры
    duration_months: Mapped[int] = mapped_column(Integer, default=1)  # на какой период дается
    max_uses: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # макс. использований
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Подарочный промокод (для конкретного пользователя)
    for_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)  # ID получателя подарка
    is_gift: Mapped[bool] = mapped_column(Boolean, default=False)  # флаг подарочного промокода
    
    # Срок действия
    valid_from: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Статус
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_by: Mapped[int] = mapped_column(BigInteger)  # ID админа

    def __repr__(self):
        return f"<Promocode {self.code} ({self.discount_type})>"


class Payment(Base):
    """История платежей через Prodamus"""
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    
    # Данные платежа
    order_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(10), default="RUB")
    
    # Тип подписки
    subscription_plan: Mapped[str] = mapped_column(String(20))  # '1_month', '3_months', etc
    duration_months: Mapped[int] = mapped_column(Integer)
    
    # Статус
    status: Mapped[str] = mapped_column(String(20))  # 'pending', 'success', 'failed', 'refunded'
    payment_method: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Даты
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Связи
    user: Mapped["User"] = relationship(back_populates="payments")

    def __repr__(self):
        return f"<Payment {self.order_id} user={self.user_id} {self.amount} {self.currency}>"


class Broadcast(Base):
    """История рассылок"""
    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Содержимое
    message_text: Mapped[str] = mapped_column(Text)
    media_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # 'photo', 'video', 'document'
    media_file_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    # Параметры
    target_audience: Mapped[str] = mapped_column(String(20))  # 'all', 'active', 'expired'
    button_text: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    button_url: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    # Статистика
    total_sent: Mapped[int] = mapped_column(Integer, default=0)
    total_failed: Mapped[int] = mapped_column(Integer, default=0)
    
    # Даты
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[int] = mapped_column(BigInteger)  # ID админа

    def __repr__(self):
        return f"<Broadcast {self.id} sent={self.total_sent}>"


class BotText(Base):
    """Редактируемые тексты бота"""
    __tablename__ = "bot_texts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, index=True)  # Уникальный ключ текста
    text: Mapped[str] = mapped_column(Text)  # Сам текст
    description: Mapped[str] = mapped_column(String(255))  # Описание для админа
    
    # Метаданные
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)  # ID админа

    def __repr__(self):
        return f"<BotText {self.key}>"
