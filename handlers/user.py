"""
handlers/user.py
"""
import json, logging
from aiogram import Router, types, F
from aiogram.filters import CommandStart, Command

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from utils.keyboards import order_action_kb, lang_selection_kb, main_menu_kb
from database.crud import create_order, get_product, get_all_products, update_user_lang
from database.models import Order, User
from config import settings
from utils.localization import get_text

logger = logging.getLogger(__name__)
router = Router()

@router.message(Command("id"))
async def cmd_get_id(message: types.Message):
    """Guruh yoki shaxsiy chat ID raqamini olish uchun yordamchi buyruq."""
    await message.answer(
        f"🆔 Ushbu chat ID raqami: <code>{message.chat.id}</code>",
        parse_mode="HTML"
    )

async def get_user_lang_by_id(session: AsyncSession, telegram_id: int) -> str:
    r = await session.execute(select(User.language_code).where(User.telegram_id == telegram_id))
    row = r.first()
    return row[0] if row and row[0] else "uz"

@router.message(CommandStart())
async def cmd_start(message: types.Message, db_user, is_new_user: bool, session: AsyncSession):
    if not db_user.language_code or db_user.language_code not in ("uz", "zh"):
        await message.answer(
            "🇺🇿 Iltimos, tilni tanlang:\n🇨🇳 请选择语言:",
            reply_markup=lang_selection_kb()
        )
    else:
        lang = db_user.language_code
        greeting = get_text("greeting_new" if is_new_user else "greeting_returning", lang)
        prompt = get_text("order_btn_prompt", lang)
        await message.answer(
            f"{greeting}, <b>{db_user.full_name}</b>!\n\n{prompt}",
            reply_markup=main_menu_kb(lang),
            parse_mode="HTML",
        )

@router.callback_query(F.data.startswith("setlang:"))
async def cb_setlang(callback: types.CallbackQuery, session: AsyncSession):
    lang = callback.data.split(":")[1]
    await update_user_lang(session, callback.from_user.id, lang)
    msg = get_text("lang_changed", lang)
    await callback.message.answer(msg, reply_markup=main_menu_kb(lang))
    await callback.message.delete()
    await callback.answer()

@router.message(lambda m: m.text and any(x in m.text for x in ["Til", "Language", "语言"]))
async def cmd_change_lang(message: types.Message):
    await message.answer(
        "🇺🇿 Iltimos, tilni tanlang:\n🇨🇳 请选择语言:",
        reply_markup=lang_selection_kb()
    )

@router.message(lambda m: m.web_app_data is not None)
async def webapp_data(message: types.Message, db_user, session: AsyncSession):
    raw = message.web_app_data.data
    lang = db_user.language_code or "uz"
    try:
        data = json.loads(raw)
        action = data.get("action", "")

        if action == "order":
            items    = data.get("items", [])
            total    = float(data.get("total", 0))
            customer = data.get("customer", {})
            payment  = data.get("payment", "—")

            # Save orders in DB
            order_ids = []
            for item in items:
                order = await create_order(
                    session,
                    user_id=db_user.telegram_id,
                    product=item.get("name", "—"),
                    quantity=int(item.get("qty", 1)),
                    price=float(item.get("total", 0)),
                    product_id=item.get("id"),
                )
                order.note = (
                    f"Ism: {customer.get('name','—')} | "
                    f"Tel: {customer.get('phone','—')} | "
                    f"Manzil: {customer.get('address','—')} | "
                    f"To'lov: {payment}"
                )
                await session.commit()
                order_ids.append(f"#{order.id}")

            order_num = order_ids[0] if order_ids else "#—"

            # Notify admins in their language
            pay_icon = "⚡ Click" if payment == "click" else "💜 Payme"
            items_text = "\n".join(
                f"  • {i.get('name')} × {i.get('qty')} = {int(i.get('total',0)):,} so'm"
                for i in items
            )

            for admin_id in settings.admin_list:
                admin_lang = await get_user_lang_by_id(session, admin_id)
                admin_text = (
                    f"🛒 <b>{get_text('orders', admin_lang)} {order_num}</b>\n\n"
                    f"👤 {db_user.full_name} (<code>{db_user.telegram_id}</code>)\n"
                    f"📦 <b>{get_text('products', admin_lang)}:</b>\n{items_text}\n"
                    f"💰 <b>{get_text('stats', admin_lang)}: {int(total):,} so'm</b>\n\n"
                    f"━━━━━━━━━━━━━━━━━\n"
                    f"👤 Ism: {customer.get('name','—')}\n"
                    f"📞 Tel: {customer.get('phone','—')}\n"
                    f"📍 Manzil: {customer.get('address','—')}\n"
                    f"💬 Izoh: {customer.get('note','—')}\n"
                    f"💳 To'lov: {pay_icon}"
                )
                try:
                    await message.bot.send_message(
                        admin_id, admin_text,
                        parse_mode="HTML",
                        reply_markup=order_action_kb(
                            int(order_ids[0].replace("#","")) if order_ids else 0,
                            admin_lang
                        ),
                    )
                except Exception as e:
                    logger.error(f"Admin notify error: {e}")

            # Respond to user
            await message.answer(
                f"✅ <b>{get_text('order_confirmed', lang)}!</b>\n\n"
                f"🧾 Raqam: <b>{order_num}</b>\n"
                f"💰 Jami: <b>{int(total):,} so'm</b>\n\n"
                f"📞 Tez orada bog'lanamiz, {customer.get('name','')}.  🙏",
                parse_mode="HTML",
            )
            
            # Google Sheets auto sync call (will run dynamically if Sheets module is loaded)
            try:
                from utils.sheets import sync_to_sheets
                import asyncio
                # run sync as a background task so it doesn't block telegram response
                asyncio.create_task(sync_to_sheets())
            except Exception as e:
                logger.error(f"Auto-sync sheets error: {e}")

        else:
            await message.answer("✅ Qabul qilindi!", parse_mode="HTML")

    except Exception as e:
        logger.error(f"WebApp data error: {e}")
        await message.answer("✅ Buyurtma qabul qilindi!", parse_mode="HTML")

@router.callback_query(F.data.startswith("order_"))
async def order_callback(callback: types.CallbackQuery, session: AsyncSession):
    action, oid = callback.data.split(":")
    from database.crud import update_order_status
    status = "confirmed" if action == "order_confirm" else "cancelled"
    await update_order_status(session, int(oid), status)
    
    # Get user language code to translate status update
    lang = await get_user_lang_by_id(session, callback.from_user.id)
    label = get_text("order_confirmed", lang) if status == "confirmed" else get_text("order_cancelled", lang)
    
    await callback.message.edit_text(
        callback.message.text + f"\n\n<b>{label}</b>", parse_mode="HTML"
    )
    await callback.answer(label)
    
    # Google Sheets auto sync call
    try:
        from utils.sheets import sync_to_sheets
        import asyncio
        asyncio.create_task(sync_to_sheets())
    except Exception as e:
        logger.error(f"Auto-sync sheets error: {e}")
