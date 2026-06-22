from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from config import settings
from database.models import AsyncSessionLocal
from database.crud import get_or_create_user
from sqlalchemy.ext.asyncio import AsyncSession
import logging

logger = logging.getLogger(__name__)

class DatabaseMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        async with AsyncSessionLocal() as session:
            data["session"] = session
            tg_user = None
            if isinstance(event, Message) and event.from_user:
                tg_user = event.from_user
                logger.info(f"📩 MSG RECEIVED: text='{event.text}', chat_id={event.chat.id}, type='{event.chat.type}', from_id={tg_user.id}")
            elif isinstance(event, CallbackQuery) and event.from_user:
                tg_user = event.from_user
                logger.info(f"📩 CALLBACK RECEIVED: data='{event.data}', from_id={tg_user.id}")
            if tg_user and not tg_user.is_bot:
                user, created = await get_or_create_user(session, tg_user)
                # Sync roles from configuration
                if user.telegram_id in settings.admin_list:
                    if user.role != "bosh_admin":
                        user.role = "bosh_admin"
                        await session.commit()
                elif user.telegram_id in settings.sklad_list:
                    if user.role != "sklad":
                        user.role = "sklad"
                        await session.commit()
                else:
                    if user.role in ("bosh_admin", "sklad"):
                        user.role = "user"
                        await session.commit()
                
                data["db_user"] = user
                data["is_new_user"] = created
                data["needs_lang_selection"] = user.language_code not in ("uz", "zh")
            return await handler(event, data)

class BanCheckMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        db_user = data.get("db_user")
        if db_user and db_user.is_banned:
            if isinstance(event, Message):
                await event.answer("🚫 Siz botdan bloklangansiz.")
            return
        return await handler(event, data)

class AdminMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        uid = None
        if isinstance(event, Message) and event.from_user:
            uid = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            uid = event.from_user.id
        
        is_bosh = uid in settings.admin_list
        is_sklad = uid in settings.sklad_list
        
        data["is_bosh_admin"] = is_bosh
        data["is_sklad"] = is_sklad
        data["is_admin"] = is_bosh or is_sklad
        return await handler(event, data)
