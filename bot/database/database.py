import os
from datetime import datetime
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, update, delete, func
from sqlalchemy.orm import selectinload

from .models import Base, User, Subscription, Promocode, Payment, Broadcast


class Database:
    def __init__(self, db_url: str):
        self.engine = create_async_engine(db_url, echo=False)
        self.session_maker = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

    async def init_db(self):
        """Создание таблиц"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def get_session(self) -> AsyncSession:
        """Получить сессию БД"""
        async with self.session_maker() as session:
            return session

    # ============ USERS ============
    
    async def add_user(self, user_id: int, username: str = None, first_name: str = None, last_name: str = None) -> User:
        """Добавить или обновить пользователя"""
        async with self.session_maker() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            
            if user:
                user.username = username
                user.first_name = first_name
                user.last_name = last_name
                user.last_activity = datetime.utcnow()
            else:
                user = User(
                    id=user_id,
                    username=username,
                    first_name=first_name,
                    last_name=last_name
                )
                session.add(user)
            
            await session.commit()
            await session.refresh(user)
            return user

    async def get_user(self, user_id: int) -> Optional[User]:
        """Получить пользователя"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(User)
                .options(selectinload(User.subscriptions))
                .where(User.id == user_id)
            )
            return result.scalar_one_or_none()

    async def update_subscription_status(self, user_id: int, is_subscribed: bool, expires_at: datetime = None):
        """Обновить статус подписки пользователя"""
        async with self.session_maker() as session:
            await session.execute(
                update(User)
                .where(User.id == user_id)
                .values(is_subscribed=is_subscribed, subscription_until=expires_at)
            )
            await session.commit()

    async def get_all_users(self) -> List[User]:
        """Получить всех пользователей"""
        async with self.session_maker() as session:
            result = await session.execute(select(User))
            return result.scalars().all()

    async def get_active_subscribers(self) -> List[User]:
        """Получить активных подписчиков"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(User).where(User.is_subscribed == True)
            )
            return result.scalars().all()

    async def get_expired_subscribers(self) -> List[User]:
        """Получить пользователей с истекшей подпиской"""
        async with self.session_maker() as session:
            now = datetime.utcnow()
            result = await session.execute(
                select(User).where(
                    User.is_subscribed == True,
                    User.subscription_until < now
                )
            )
            return result.scalars().all()

    # ============ SUBSCRIPTIONS ============

    async def add_subscription(
        self,
        user_id: int,
        duration_months: int,
        expires_at: datetime,
        activated_by: str = "payment",
        promocode: str = None
    ) -> Subscription:
        """Добавить подписку"""
        async with self.session_maker() as session:
            subscription = Subscription(
                user_id=user_id,
                duration_months=duration_months,
                expires_at=expires_at,
                activated_by=activated_by,
                promocode=promocode
            )
            session.add(subscription)
            
            # Обновить статус пользователя
            await session.execute(
                update(User)
                .where(User.id == user_id)
                .values(is_subscribed=True, subscription_until=expires_at)
            )
            
            await session.commit()
            await session.refresh(subscription)
            return subscription

    async def get_user_subscriptions(self, user_id: int) -> List[Subscription]:
        """Получить историю подписок пользователя"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(Subscription)
                .where(Subscription.user_id == user_id)
                .order_by(Subscription.started_at.desc())
            )
            return result.scalars().all()

    # ============ PROMOCODES ============

    async def create_promocode(
        self,
        code: str,
        discount_type: str,
        discount_value: float,
        duration_months: int,
        max_uses: int = None,
        valid_until: datetime = None,
        created_by: int = 0
    ) -> Promocode:
        """Создать промокод"""
        async with self.session_maker() as session:
            promocode = Promocode(
                code=code,
                discount_type=discount_type,
                discount_value=discount_value,
                duration_months=duration_months,
                max_uses=max_uses,
                valid_until=valid_until,
                created_by=created_by
            )
            session.add(promocode)
            await session.commit()
            await session.refresh(promocode)
            return promocode

    async def get_promocode(self, code: str) -> Optional[Promocode]:
        """Получить промокод"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(Promocode).where(Promocode.code == code.upper())
            )
            return result.scalar_one_or_none()

    async def use_promocode(self, code: str) -> bool:
        """Использовать промокод (увеличить счетчик)"""
        async with self.session_maker() as session:
            promo = await self.get_promocode(code)
            if not promo:
                return False
            
            await session.execute(
                update(Promocode)
                .where(Promocode.code == code.upper())
                .values(used_count=Promocode.used_count + 1)
            )
            await session.commit()
            return True

    async def get_all_promocodes(self) -> List[Promocode]:
        """Получить все промокоды"""
        async with self.session_maker() as session:
            result = await session.execute(select(Promocode))
            return result.scalars().all()

    # ============ PAYMENTS ============

    async def add_payment(
        self,
        user_id: int,
        order_id: str,
        amount: float,
        subscription_plan: str,
        duration_months: int,
        status: str = "pending"
    ) -> Payment:
        """Добавить платеж"""
        async with self.session_maker() as session:
            payment = Payment(
                user_id=user_id,
                order_id=order_id,
                amount=amount,
                subscription_plan=subscription_plan,
                duration_months=duration_months,
                status=status
            )
            session.add(payment)
            await session.commit()
            await session.refresh(payment)
            return payment

    async def update_payment_status(self, order_id: str, status: str):
        """Обновить статус платежа"""
        async with self.session_maker() as session:
            await session.execute(
                update(Payment)
                .where(Payment.order_id == order_id)
                .values(status=status, paid_at=datetime.utcnow() if status == "success" else None)
            )
            await session.commit()

    async def get_payment(self, order_id: str) -> Optional[Payment]:
        """Получить платеж"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(Payment).where(Payment.order_id == order_id)
            )
            return result.scalar_one_or_none()

    # ============ BROADCASTS ============

    async def add_broadcast(
        self,
        message_text: str,
        target_audience: str,
        created_by: int,
        media_type: str = None,
        media_file_id: str = None,
        button_text: str = None,
        button_url: str = None
    ) -> Broadcast:
        """Добавить рассылку"""
        async with self.session_maker() as session:
            broadcast = Broadcast(
                message_text=message_text,
                target_audience=target_audience,
                created_by=created_by,
                media_type=media_type,
                media_file_id=media_file_id,
                button_text=button_text,
                button_url=button_url
            )
            session.add(broadcast)
            await session.commit()
            await session.refresh(broadcast)
            return broadcast

    async def update_broadcast_stats(self, broadcast_id: int, sent: int, failed: int):
        """Обновить статистику рассылки"""
        async with self.session_maker() as session:
            await session.execute(
                update(Broadcast)
                .where(Broadcast.id == broadcast_id)
                .values(
                    total_sent=sent,
                    total_failed=failed,
                    sent_at=datetime.utcnow()
                )
            )
            await session.commit()

    # ============ STATISTICS ============

    async def get_statistics(self) -> dict:
        """Получить общую статистику"""
        async with self.session_maker() as session:
            total_users = await session.scalar(select(func.count(User.id)))
            active_subs = await session.scalar(
                select(func.count(User.id)).where(User.is_subscribed == True)
            )
            total_revenue = await session.scalar(
                select(func.sum(Payment.amount)).where(Payment.status == "success")
            ) or 0
            
            return {
                "total_users": total_users,
                "active_subscribers": active_subs,
                "total_revenue": total_revenue
            }
