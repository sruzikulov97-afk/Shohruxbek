"""
bot.py — asosiy kirish nuqtasi
"""
import asyncio, logging, sys, os, os
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import settings
from database.models import init_db
from middlewares import DatabaseMiddleware, BanCheckMiddleware, AdminMiddleware
from handlers import user_router, admin_router

os.makedirs("data", exist_ok=True)
logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("data/bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

bot = Bot(token=settings.bot_token,
          default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp  = Dispatcher(storage=MemoryStorage())

for mw in [DatabaseMiddleware(), BanCheckMiddleware(), AdminMiddleware()]:
    dp.message.middleware(mw)
    dp.callback_query.middleware(mw)

dp.include_router(admin_router)
dp.include_router(user_router)


async def on_startup():
    await init_db()
    me = await bot.get_me()
    logger.info(f"✅ Bot ishga tushdi: @{me.username}")

    # ── Har bir rol uchun alohida buyruqlar ro'yxatini o'rnatish ──
    from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat

    # Barcha foydalanuvchilar uchun default buyruqlar
    await bot.set_my_commands(
        [BotCommand(command="start", description="🏠 Botni boshlash / Buyurtma berish")],
        scope=BotCommandScopeDefault(),
    )

    # Bosh Admin uchun alohida buyruqlar (har bir admin ID uchun)
    for aid in settings.admin_list:
        try:
            await bot.set_my_commands(
                [
                    BotCommand(command="start",  description="🏠 Asosiy menyu"),
                    BotCommand(command="admin",  description="⚙️ Bosh Admin paneli"),
                    BotCommand(command="ban",    description="🚫 Foydalanuvchini bloklash"),
                    BotCommand(command="unban",  description="✅ Blokdan chiqarish"),
                ],
                scope=BotCommandScopeChat(chat_id=aid),
            )
        except Exception:
            pass

    # Sklad Admin uchun alohida buyruqlar (har bir sklad ID uchun)
    for sid in settings.sklad_list:
        try:
            await bot.set_my_commands(
                [
                    BotCommand(command="start", description="🏠 Asosiy menyu"),
                    BotCommand(command="sklad", description="📦 Sklad paneli"),
                ],
                scope=BotCommandScopeChat(chat_id=sid),
            )
        except Exception:
            pass

    for aid in settings.admin_list:
        try: await bot.send_message(aid, f"✅ <b>Bot ishga tushdi!</b> @{me.username}")
        except Exception: pass

async def on_shutdown():
    for aid in settings.admin_list:
        try: await bot.send_message(aid, "🛑 <b>Bot to'xtatildi.</b>")
        except Exception: pass
    await bot.session.close()

async def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # API + Static server
    from aiohttp import web
    from api_server import create_app
    api_app = create_app()
    runner = web.AppRunner(api_app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"✅ Server: http://0.0.0.0:{port}")

    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
