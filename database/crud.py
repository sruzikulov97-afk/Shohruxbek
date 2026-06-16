"""
database/crud.py
"""
from datetime import datetime
from typing import Optional, List
from sqlalchemy import select, update, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import User, Product, Order, BroadcastLog, StockTransaction


# ── User ──────────────────────────────────────────────────────────────────────

async def get_or_create_user(session: AsyncSession, tg_user) -> tuple:
    r = await session.execute(select(User).where(User.telegram_id == tg_user.id))
    user = r.scalar_one_or_none()
    if user:
        user.username = tg_user.username
        user.first_name = tg_user.first_name
        user.last_name = tg_user.last_name
        user.last_active = datetime.utcnow()
        await session.commit()
        return user, False
    user = User(
        telegram_id=tg_user.id, username=tg_user.username,
        first_name=tg_user.first_name, last_name=tg_user.last_name,
        language_code=tg_user.language_code, is_bot=tg_user.is_bot,
    )
    session.add(user); await session.commit(); await session.refresh(user)
    return user, True

async def get_all_users(session: AsyncSession, limit=500) -> List[User]:
    r = await session.execute(select(User).order_by(desc(User.created_at)).limit(limit))
    return r.scalars().all()

async def get_user_count(session: AsyncSession) -> int:
    return (await session.execute(select(func.count(User.id)))).scalar_one()

async def get_active_user_ids(session: AsyncSession) -> List[int]:
    r = await session.execute(select(User.telegram_id).where(User.is_banned == False))
    return [row[0] for row in r.all()]

async def ban_user(session: AsyncSession, tid: int) -> bool:
    r = await session.execute(update(User).where(User.telegram_id == tid).values(is_banned=True))
    await session.commit(); return r.rowcount > 0

async def unban_user(session: AsyncSession, tid: int) -> bool:
    r = await session.execute(update(User).where(User.telegram_id == tid).values(is_banned=False))
    await session.commit(); return r.rowcount > 0


# ── Product ───────────────────────────────────────────────────────────────────

async def get_all_products(session: AsyncSession, only_active=False) -> List[Product]:
    q = select(Product).order_by(Product.id)
    if only_active:
        q = q.where(Product.is_active == True)
    return (await session.execute(q)).scalars().all()

async def get_product(session: AsyncSession, pid: int) -> Optional[Product]:
    return (await session.execute(select(Product).where(Product.id == pid))).scalar_one_or_none()

async def create_product(session: AsyncSession, name: str, price: float,
                         photo_url: str = None, category: str = "Asosiy",
                         description: str = "", stock: int = 0, added_by: int = None) -> Product:
    p = Product(name=name, price=price, photo_url=photo_url, category=category, description=description, stock=stock)
    session.add(p); await session.commit(); await session.refresh(p)
    if stock > 0:
        tx = StockTransaction(product_id=p.id, quantity=stock, type="initial", added_by=added_by)
        session.add(tx); await session.commit()
    return p

async def add_stock(session: AsyncSession, pid: int, qty: int, added_by: int) -> bool:
    p = await get_product(session, pid)
    if not p: return False
    p.stock = (p.stock or 0) + qty
    tx = StockTransaction(product_id=pid, quantity=qty, type="addition", added_by=added_by)
    session.add(tx)
    await session.commit()
    return True

async def update_user_lang(session: AsyncSession, telegram_id: int, lang: str) -> bool:
    r = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = r.scalar_one_or_none()
    if not user: return False
    user.language_code = lang
    await session.commit()
    return True

async def update_product(session: AsyncSession, pid: int, **kwargs) -> bool:
    kwargs["updated_at"] = datetime.utcnow()
    r = await session.execute(update(Product).where(Product.id == pid).values(**kwargs))
    await session.commit(); return r.rowcount > 0

async def delete_product(session: AsyncSession, pid: int) -> bool:
    p = await get_product(session, pid)
    if not p: return False
    await session.delete(p); await session.commit(); return True

async def toggle_product(session: AsyncSession, pid: int) -> Optional[bool]:
    p = await get_product(session, pid)
    if not p: return None
    p.is_active = not p.is_active
    await session.commit(); return p.is_active


# ── Order ─────────────────────────────────────────────────────────────────────

async def create_order(session: AsyncSession, user_id: int, product: str,
                       quantity: int, price: float, product_id: int = None) -> Order:
    o = Order(user_id=user_id, product=product, quantity=quantity,
              price=price, product_id=product_id)
    session.add(o); await session.commit(); await session.refresh(o)
    return o

async def get_orders(session: AsyncSession, limit=100) -> List[Order]:
    r = await session.execute(select(Order).order_by(desc(Order.created_at)).limit(limit))
    return r.scalars().all()

async def get_order_count(session: AsyncSession) -> int:
    return (await session.execute(select(func.count(Order.id)))).scalar_one()

async def update_order_status(session: AsyncSession, oid: int, status: str) -> bool:
    r = await session.execute(select(Order).where(Order.id == oid))
    order = r.scalar_one_or_none()
    if not order: return False
    old_status = order.status
    order.status = status
    if status == "confirmed" and old_status != "confirmed":
        if order.product_id:
            p = await get_product(session, order.product_id)
            if p:
                p.stock = max(0, (p.stock or 0) - (order.quantity or 1))
    await session.commit()
    return True

async def get_total_revenue(session: AsyncSession) -> float:
    r = await session.execute(
        select(func.sum(Order.price)).where(Order.status == "confirmed"))
    return r.scalar_one() or 0.0


# ── Broadcast ─────────────────────────────────────────────────────────────────

async def save_broadcast(session: AsyncSession, admin_id: int, text: str,
                         sent: int, failed: int) -> BroadcastLog:
    log = BroadcastLog(admin_id=admin_id, message_text=text,
                       total_sent=sent, total_failed=failed)
    session.add(log); await session.commit(); return log

async def get_broadcasts(session: AsyncSession, limit=50) -> List[BroadcastLog]:
    r = await session.execute(
        select(BroadcastLog).order_by(desc(BroadcastLog.created_at)).limit(limit))
    return r.scalars().all()
