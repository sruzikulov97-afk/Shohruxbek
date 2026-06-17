"""
handlers/admin.py
"""
import asyncio, logging
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from utils.filters import IsBoshAdmin, IsSklad, IsAnyAdmin
from utils.keyboards import bosh_admin_menu_kb, sklad_menu_kb, cancel_kb, product_manage_kb
from handlers.user import get_user_lang_by_id
from database.crud import (
    get_user_count, get_order_count, get_total_revenue,
    get_all_users, get_active_user_ids, get_orders, get_broadcasts,
    ban_user, unban_user, save_broadcast,
    get_all_products, get_product, create_product, update_product,
    delete_product, toggle_product, update_order_status, add_stock
)
from utils.localization import get_text
from config import settings

logger = logging.getLogger(__name__)
router = Router()
router.message.filter(IsAnyAdmin())


# ── FSM States ──────────────────────────────────────────────────────────────

class ProductAdd(StatesGroup):
    name     = State()
    price    = State()
    photo    = State()
    category = State()
    desc     = State()
    stock    = State()

class ProductEdit(StatesGroup):
    field = State()
    value = State()

class BroadcastSt(StatesGroup):
    text    = State()
    confirm = State()

class ProductStockAdd(StatesGroup):
    qty = State()


# ── /admin ──────────────────────────────────────────────────────────────────

@router.message(Command("admin"))
async def cmd_admin(message: types.Message, state: FSMContext, session: AsyncSession):
    await state.clear()
    uid = message.from_user.id
    lang = await get_user_lang_by_id(session, uid)
    if uid in settings.admin_list:
        await message.answer(get_text("admin_panel", lang), reply_markup=bosh_admin_menu_kb(lang), parse_mode="HTML")
    elif uid in settings.sklad_list:
        await message.answer(get_text("sklad_panel_welcome", lang), reply_markup=sklad_menu_kb(lang), parse_mode="HTML")


@router.message(F.text.in_(["🔙 Orqaga", "🔙 返回"]))
async def back_main(message: types.Message, state: FSMContext, session: AsyncSession):
    await state.clear()
    lang = await get_user_lang_by_id(session, message.from_user.id)
    from utils.keyboards import main_menu_kb
    await message.answer("🏠 Asosiy menyu / 主菜单", reply_markup=main_menu_kb(lang))


# ── Google Sheets Sync ───────────────────────────────────────────────────────

@router.message(F.text.in_(["📊 Google Sheets", "📊 谷歌表格"]), IsBoshAdmin())
async def export_sheets(message: types.Message, session: AsyncSession):
    lang = await get_user_lang_by_id(session, message.from_user.id)
    await message.answer(get_text("sheets_syncing", lang))
    try:
        from utils.sheets import sync_to_sheets
        sheet_url = await sync_to_sheets()
        if sheet_url:
            await message.answer(get_text("sheets_success", lang, sheet_url))
        else:
            await message.answer(get_text("sheets_error", lang, "Google Sheets credentials are not configured."))
    except Exception as e:
        logger.error(f"Manual sheets sync error: {e}")
        await message.answer(get_text("sheets_error", lang, str(e)))


# ── Sklad: Mahsulot qo'shish (Sklad faqat shu tugmani ko'radi) ───────────────

@router.message(F.text.in_(["➕ Mahsulot qo'shish", "➕ 添加产品"]))
async def sklad_add_product_btn(message: types.Message, state: FSMContext, session: AsyncSession):
    """Sklad admin faqat yangi mahsulot qo'sha oladi (nofaol holda saqlanadi)."""
    lang = await get_user_lang_by_id(session, message.from_user.id)
    await state.set_state(ProductAdd.name)
    await message.answer(
        f"➕ <b>{get_text('prod_new', lang)}</b>\n\n1/6 — Nomini kiriting:",
        parse_mode="HTML", reply_markup=cancel_kb(lang)
    )


# ── Bosh Admin: Sotuvga chiqarish (kutayotgan mahsulotlar) ───────────────────

@router.message(F.text.in_(["📢 Sotuvga chiqarish", "📢 上架销售"]), IsBoshAdmin())
async def pending_products_list(message: types.Message, session: AsyncSession):
    """Bosh admin skladchi qo'shgan (nofaol) mahsulotlarni ko'radi va sotuvga chiqaradi."""
    lang = await get_user_lang_by_id(session, message.from_user.id)
    prods = await get_all_products(session)
    pending = [p for p in prods if not p.is_active]
    if not pending:
        await message.answer(get_text("no_pending", lang), parse_mode="HTML")
        return
    b = InlineKeyboardBuilder()
    for p in pending:
        b.button(
            text=f"📦 {p.name} — {int(p.price):,} so'm | Sklad: {p.stock or 0} ta",
            callback_data=f"prod_publish:{p.id}"
        )
    b.adjust(1)
    await message.answer(
        f"🕐 <b>{get_text('pending_products', lang)} ({len(pending)} ta):</b>\n\n"
        f"Sotuvga chiqarish uchun mahsulotni tanlang:",
        reply_markup=b.as_markup(), parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("prod_publish:"))
async def prod_publish(callback: types.CallbackQuery, session: AsyncSession):
    """Mahsulotni faollashtirish (sotuvga chiqarish)."""
    lang = await get_user_lang_by_id(session, callback.from_user.id)
    pid = int(callback.data.split(":")[1])
    p = await get_product(session, pid)
    if not p:
        await callback.answer("Topilmadi"); return
    p.is_active = True
    await session.commit()
    # Sync Sheets in background
    try:
        from utils.sheets import sync_to_sheets
        asyncio.create_task(sync_to_sheets())
    except Exception as e:
        logger.error(f"Sheets sync error: {e}")
    await callback.message.edit_text(
        get_text("published_ok", lang, p.name), parse_mode="HTML"
    )
    await callback.answer("✅ Sotuvga chiqarildi!")


# ── Statistika ───────────────────────────────────────────────────────────────

@router.message(F.text.in_(["📊 Statistika", "📊 统计数据"]), IsBoshAdmin())
async def stats(message: types.Message, session: AsyncSession):
    lang = await get_user_lang_by_id(session, message.from_user.id)
    users   = await get_user_count(session)
    orders  = await get_order_count(session)
    revenue = await get_total_revenue(session)
    prods   = await get_all_products(session)
    bcs     = await get_broadcasts(session, limit=1000)
    await message.answer(
        get_text("stats_text", lang, users, len(prods), orders, int(revenue), len(bcs)),
        parse_mode="HTML",
    )


# ── Foydalanuvchilar ─────────────────────────────────────────────────────────

@router.message(F.text.in_(["👥 Foydalanuvchilar", "👥 用户列表"]), IsBoshAdmin())
async def users_list(message: types.Message, session: AsyncSession):
    lang = await get_user_lang_by_id(session, message.from_user.id)
    users = await get_all_users(session, limit=30)
    total = await get_user_count(session)
    text = get_text("users_header", lang, total)
    for u in users:
        icon = "🚫" if u.is_banned else "✅"
        text += f"{icon} {u.full_name} | <code>{u.telegram_id}</code>\n"
    await message.answer(text[:4096], parse_mode="HTML")


@router.message(Command("ban"), IsBoshAdmin())
async def ban_cmd(message: types.Message, session: AsyncSession):
    args = message.text.split()
    if len(args) < 2: await message.answer("❗ /ban <id>"); return
    try:
        ok = await ban_user(session, int(args[1]))
        await message.answer(f"{'🚫 Bloklandi' if ok else '❌ Topilmadi'}: <code>{args[1]}</code>", parse_mode="HTML")
    except ValueError:
        await message.answer("❗ ID raqam bo'lishi kerak")


@router.message(Command("unban"), IsBoshAdmin())
async def unban_cmd(message: types.Message, session: AsyncSession):
    args = message.text.split()
    if len(args) < 2: await message.answer("❗ /unban <id>"); return
    try:
        ok = await unban_user(session, int(args[1]))
        await message.answer(f"{'✅ Blok ochildi' if ok else '❌ Topilmadi'}: <code>{args[1]}</code>", parse_mode="HTML")
    except ValueError:
        await message.answer("❗ ID raqam bo'lishi kerak")


# ── Buyurtmalar ──────────────────────────────────────────────────────────────

@router.message(F.text.in_(["📦 Buyurtmalar", "📦 订单列表"]), IsBoshAdmin())
async def orders_list(message: types.Message, session: AsyncSession):
    lang = await get_user_lang_by_id(session, message.from_user.id)
    orders = await get_orders(session, limit=20)
    if not orders:
        await message.answer(get_text("orders", lang) + " empty."); return
    icons = {"pending":"⏳","confirmed":"✅","cancelled":"❌"}
    text = get_text("orders_header", lang, len(orders))
    for o in orders:
        text += f"{icons.get(o.status,'📦')} #{o.id} | <code>{o.user_id}</code> | {o.product} x{o.quantity} = {int(o.price):,} so'm\n"
    await message.answer(text[:4096], parse_mode="HTML")


@router.message(F.text.in_(["🛍 Mahsulotlar", "🛍 产品列表"]), IsBoshAdmin())
async def products_admin(message: types.Message, session: AsyncSession):
    lang = await get_user_lang_by_id(session, message.from_user.id)
    prods = await get_all_products(session)
    b = InlineKeyboardBuilder()
    for p in prods:
        status = "🟢" if p.is_active else "🔴"
        photo  = "🖼" if p.photo_url else "📦"
        b.button(text=f"{status} {photo} {p.name} — {int(p.price):,} | S:{p.stock or 0}",
                 callback_data=f"padmin:{p.id}")
    b.button(text=get_text("prod_new", lang), callback_data="prod_new")
    b.adjust(1)
    await message.answer(
        f"🛍 <b>{get_text('products', lang)} ({len(prods)} ta):</b>\n\n"
        "🟢 Faol  |  🔴 Nofaol  |  🖼 Rasmi bor  |  📦 Rasmsiz",
        reply_markup=b.as_markup(), parse_mode="HTML",
    )


# ── Mahsulot detail ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("padmin:"))
async def product_detail(callback: types.CallbackQuery, session: AsyncSession):
    lang = await get_user_lang_by_id(session, callback.from_user.id)
    is_bosh_admin = callback.from_user.id in settings.admin_list
    pid = int(callback.data.split(":")[1])
    p = await get_product(session, pid)
    if not p: await callback.answer("Topilmadi"); return
    status = "🟢 Faol (Sotuvda)" if p.is_active else "🔴 Nofaol (Kutayotgan)"
    text = (
        f"📦 <b>{p.name}</b>\n\n"
        f"📝 {p.description or '—'}\n"
        f"💰 {int(p.price):,} so'm\n"
        f"🗂 {p.category or '—'}\n"
        f"📌 {status} | ID: {p.id}\n"
        f"📦 Sklad qoldig'i: <b>{p.stock or 0}</b> dona\n"
        f"🖼 {'Rasm bor' if p.photo_url else 'Rasm yo\'q'}"
    )
    kb = product_manage_kb(p.id, p.is_active, lang, is_bosh_admin=is_bosh_admin)
    if p.photo_url:
        try:
            await callback.message.answer_photo(p.photo_url, caption=text, parse_mode="HTML", reply_markup=kb)
            await callback.message.delete()
        except Exception:
            await callback.message.edit_text(text + f"\n🔗 {p.photo_url}", reply_markup=kb, parse_mode="HTML")
    else:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


# ── Yangi mahsulot (FSM) ─────────────────────────────────────────────────────

@router.callback_query(F.data == "prod_new")
async def prod_new_start(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    lang = await get_user_lang_by_id(session, callback.from_user.id)
    await state.set_state(ProductAdd.name)
    await callback.message.answer(
        f"➕ <b>{get_text('prod_new', lang)}</b>\n\n1/6 — Nomini kiriting:",
        parse_mode="HTML", reply_markup=cancel_kb(lang)
    )
    await callback.answer()


@router.message(ProductAdd.name)
async def prod_name(message: types.Message, state: FSMContext, session: AsyncSession):
    lang = await get_user_lang_by_id(session, message.from_user.id)
    menu_kb = bosh_admin_menu_kb(lang) if message.from_user.id in settings.admin_list else sklad_menu_kb(lang)
    if message.text in (get_text("cancel", "uz"), get_text("cancel", "zh")):
        await state.clear(); await message.answer("❌", reply_markup=menu_kb); return
    await state.update_data(name=message.text)
    await state.set_state(ProductAdd.price)
    await message.answer("2/6 — Narxini kiriting (so'mda, faqat raqam):")


@router.message(ProductAdd.price)
async def prod_price(message: types.Message, state: FSMContext, session: AsyncSession):
    lang = await get_user_lang_by_id(session, message.from_user.id)
    menu_kb = bosh_admin_menu_kb(lang) if message.from_user.id in settings.admin_list else sklad_menu_kb(lang)
    if message.text in (get_text("cancel", "uz"), get_text("cancel", "zh")):
        await state.clear(); await message.answer("❌", reply_markup=menu_kb); return
    try:
        price = float(message.text.replace(" ", "").replace(",", "."))
    except ValueError:
        await message.answer("❗ Faqat raqam kiriting:"); return
    await state.update_data(price=price)
    await state.set_state(ProductAdd.photo)
    await message.answer(
        "3/6 — Rasm URL sini yuboring 🖼\n\n"
        "Rasm yo'q bo'lsa <b>yoq</b> deb yozing.",
        parse_mode="HTML"
    )


@router.message(ProductAdd.photo)
async def prod_photo(message: types.Message, state: FSMContext, session: AsyncSession):
    lang = await get_user_lang_by_id(session, message.from_user.id)
    menu_kb = bosh_admin_menu_kb(lang) if message.from_user.id in settings.admin_list else sklad_menu_kb(lang)
    if message.text in (get_text("cancel", "uz"), get_text("cancel", "zh")):
        await state.clear(); await message.answer("❌", reply_markup=menu_kb); return

    photo_url = None
    if message.text and message.text.lower() not in ("yoq", "yo'q", "-", "skip", "no"):
        url = message.text.strip()
        if url.startswith("http"):
            photo_url = url
        else:
            await message.answer("❗ To'g'ri URL kiriting yoki yoq deb yozing:")
            return

    await state.update_data(photo_url=photo_url)
    await state.set_state(ProductAdd.category)
    await message.answer("4/6 — Kategoriyani kiriting (masalan: Ovqat, Ichimlik):")


@router.message(ProductAdd.category)
async def prod_category(message: types.Message, state: FSMContext, session: AsyncSession):
    lang = await get_user_lang_by_id(session, message.from_user.id)
    menu_kb = bosh_admin_menu_kb(lang) if message.from_user.id in settings.admin_list else sklad_menu_kb(lang)
    if message.text in (get_text("cancel", "uz"), get_text("cancel", "zh")):
        await state.clear(); await message.answer("❌", reply_markup=menu_kb); return
    await state.update_data(category=message.text.strip())
    await state.set_state(ProductAdd.desc)
    await message.answer("5/6 — Tavsifni kiriting (yoki yoq deb yozing):")


@router.message(ProductAdd.desc)
async def prod_desc(message: types.Message, state: FSMContext, session: AsyncSession):
    lang = await get_user_lang_by_id(session, message.from_user.id)
    menu_kb = bosh_admin_menu_kb(lang) if message.from_user.id in settings.admin_list else sklad_menu_kb(lang)
    if message.text in (get_text("cancel", "uz"), get_text("cancel", "zh")):
        await state.clear(); await message.answer("❌", reply_markup=menu_kb); return
    desc = "" if message.text.lower() in ("yo'q", "yoq", "-", "no") else message.text
    await state.update_data(description=desc)
    await state.set_state(ProductAdd.stock)
    await message.answer(get_text("initial_stock_prompt", lang))


@router.message(ProductAdd.stock)
async def prod_stock_finish(message: types.Message, state: FSMContext, session: AsyncSession):
    lang = await get_user_lang_by_id(session, message.from_user.id)
    is_bosh = message.from_user.id in settings.admin_list
    menu_kb = bosh_admin_menu_kb(lang) if is_bosh else sklad_menu_kb(lang)
    if message.text in (get_text("cancel", "uz"), get_text("cancel", "zh")):
        await state.clear(); await message.answer("❌", reply_markup=menu_kb); return
    try:
        stock = int(message.text)
    except ValueError:
        await message.answer(get_text("invalid_number", lang)); return

    data = await state.get_data()
    # Agar sklad admin qo'shsa — mahsulot nofaol holda (is_active=False) saqlanadi
    # Bosh admin qo'shsa — faol holda saqlanadi
    p = await create_product(
        session,
        name=data["name"], price=data["price"],
        photo_url=data.get("photo_url"),
        category=data["category"], description=data["description"],
        stock=stock, added_by=message.from_user.id,
        is_active=is_bosh  # Bosh admin: True, Sklad: False
    )
    await state.clear()
    
    # Sync Google Sheets in background
    try:
        from utils.sheets import sync_to_sheets
        asyncio.create_task(sync_to_sheets())
    except Exception as e:
        logger.error(f"Sheets sync error: {e}")

    # Bosh adminga xabar: faol, Skladdagi: nofaol (kutayotgan)
    status_note = "🟢 Sotuvda" if is_bosh else "🔴 Kutayotgan (Bosh Admin sotuvga chiqaradi)"
    text = (
        f"✅ <b>{get_text('prod_new', lang)}</b>\n\n"
        f"📦 <b>{p.name}</b>\n"
        f"💰 {int(p.price):,} so'm\n"
        f"🗂 {p.category}\n"
        f"📦 Sklad: <b>{p.stock}</b> dona\n"
        f"📌 {status_note}\n"
        f"🖼 {'Rasm bor ✅' if p.photo_url else 'Rasmsiz'}"
    )
    if p.photo_url:
        try:
            await message.answer_photo(p.photo_url, caption=text, parse_mode="HTML", reply_markup=menu_kb)
        except Exception:
            await message.answer(text + f"\n\n⚠️ Rasm yuklanmadi", reply_markup=menu_kb, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=menu_kb, parse_mode="HTML")


# ── Add Stock to existing product ───────────────────────────────────────────

@router.callback_query(F.data.startswith("prod_addstock:"))
async def add_stock_start(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    lang = await get_user_lang_by_id(session, callback.from_user.id)
    pid = int(callback.data.split(":")[1])
    await state.update_data(stock_pid=pid)
    await state.set_state(ProductStockAdd.qty)
    await callback.message.answer(get_text("enter_stock_qty", lang), reply_markup=cancel_kb(lang))
    await callback.answer()


@router.message(ProductStockAdd.qty)
async def add_stock_finish(message: types.Message, state: FSMContext, session: AsyncSession):
    lang = await get_user_lang_by_id(session, message.from_user.id)
    menu_kb = bosh_admin_menu_kb(lang) if message.from_user.id in settings.admin_list else sklad_menu_kb(lang)
    if message.text in (get_text("cancel", "uz"), get_text("cancel", "zh")):
        await state.clear(); await message.answer("❌", reply_markup=menu_kb); return
    try:
        qty = int(message.text)
        if qty <= 0: raise ValueError
    except ValueError:
        await message.answer(get_text("invalid_number", lang)); return

    data = await state.get_data()
    pid = data["stock_pid"]
    await add_stock(session, pid, qty, message.from_user.id)
    await state.clear()
    
    p = await get_product(session, pid)
    
    # Sync Google Sheets in background
    try:
        from utils.sheets import sync_to_sheets
        asyncio.create_task(sync_to_sheets())
    except Exception as e:
        logger.error(f"Sheets sync error: {e}")

    await message.answer(
        get_text("stock_added", lang, p.stock),
        reply_markup=menu_kb
    )


# ── Tahrirlash (FSM) ─────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("prod_edit:"))
async def prod_edit_start(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    lang = await get_user_lang_by_id(session, callback.from_user.id)
    pid = int(callback.data.split(":")[1])
    await state.update_data(edit_pid=pid)
    await state.set_state(ProductEdit.field)
    b = InlineKeyboardBuilder()
    for label, key in [("📛 Nom","name"),("💰 Narx","price"),("🖼 Rasm URL","photo_url"),("🗂 Kategoriya","category"),("📝 Tavsif","description"),("📦 Sklad","stock")]:
        b.button(text=label, callback_data=f"editf:{key}")
    b.button(text=get_text("cancel_btn", lang), callback_data="edit_cancel")
    b.adjust(2, 2, 2, 1)
    await callback.message.answer(get_text("field_edit_prompt", lang), reply_markup=b.as_markup())
    await callback.answer()


@router.callback_query(F.data == "edit_cancel")
async def edit_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear(); await callback.message.delete(); await callback.answer("Bekor")


@router.callback_query(F.data.startswith("editf:"), ProductEdit.field)
async def prod_edit_field(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    lang = await get_user_lang_by_id(session, callback.from_user.id)
    field = callback.data.split(":")[1]
    await state.update_data(edit_field=field)
    await state.set_state(ProductEdit.value)
    labels = {"name":"nom","price":"narx","photo_url":"rasm URL","category":"kategoriya","description":"tavsif","stock":"sklad miqdori"}
    await callback.message.answer(get_text("enter_new_val", lang, labels.get(field, field)))
    await callback.answer()


@router.message(ProductEdit.value)
async def prod_edit_value(message: types.Message, state: FSMContext, session: AsyncSession):
    lang = await get_user_lang_by_id(session, message.from_user.id)
    menu_kb = bosh_admin_menu_kb(lang) if message.from_user.id in settings.admin_list else sklad_menu_kb(lang)
    data = await state.get_data()
    pid, field = data["edit_pid"], data["edit_field"]
    value = message.text
    if field == "price":
        try: value = float(value.replace(" ","").replace(",","."))
        except ValueError: await message.answer("❗ Faqat raqam:"); return
    elif field == "stock":
        try: value = int(value)
        except ValueError: await message.answer("❗ Faqat raqam:"); return
    elif field == "photo_url":
        if not value.startswith("http"):
            await message.answer("❗ URL http... bilan boshlanishi kerak:"); return
    
    await update_product(session, pid, **{field: value})
    await state.clear()
    
    # Sync Google Sheets in background
    try:
        from utils.sheets import sync_to_sheets
        asyncio.create_task(sync_to_sheets())
    except Exception as e:
        logger.error(f"Sheets sync error: {e}")

    p = await get_product(session, pid)
    await message.answer(
        get_text("success_update", lang, p.name, p.price),
        reply_markup=menu_kb, parse_mode="HTML",
    )


# ── O'chirish ────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("prod_del:"))
async def prod_del_confirm(callback: types.CallbackQuery, session: AsyncSession):
    lang = await get_user_lang_by_id(session, callback.from_user.id)
    pid = callback.data.split(":")[1]
    b = InlineKeyboardBuilder()
    b.button(text=get_text("confirm_btn", lang), callback_data=f"prod_del_ok:{pid}")
    b.button(text=get_text("cancel_btn", lang), callback_data=f"padmin:{pid}")
    b.adjust(2)
    await callback.message.answer(get_text("confirm_del_prompt", lang), reply_markup=b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("prod_del_ok:"))
async def prod_del_exec(callback: types.CallbackQuery, session: AsyncSession):
    pid = int(callback.data.split(":")[1])
    ok = await delete_product(session, pid)
    await callback.message.edit_text("✅ O'chirildi." if ok else "❌ Topilmadi.")
    await callback.answer()


# ── Toggle ───────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("prod_toggle:"))
async def prod_toggle(callback: types.CallbackQuery, session: AsyncSession):
    lang = await get_user_lang_by_id(session, callback.from_user.id)
    pid = int(callback.data.split(":")[1])
    new_state = await toggle_product(session, pid)
    if new_state is None: await callback.answer("Topilmadi"); return
    await callback.answer("🟢 Yoqildi" if new_state else "🔴 O'chirildi", show_alert=True)
    p = await get_product(session, pid)
    status = "🟢 Faol" if p.is_active else "🔴 Nofaol"
    text = (
        f"📦 <b>{p.name}</b>\n\n"
        f"📝 {p.description or '—'}\n"
        f"💰 {int(p.price):,} so'm\n"
        f"🗂 {p.category or '—'}\n"
        f"📌 {status}\n"
        f"📦 Sklad: <b>{p.stock}</b> dona"
    )
    kb = product_manage_kb(p.id, p.is_active, lang)
    if p.photo_url:
        try:
            await callback.message.answer_photo(p.photo_url, caption=text, parse_mode="HTML", reply_markup=kb)
            await callback.message.delete()
        except Exception:
            await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


# ── Broadcast ────────────────────────────────────────────────────────────────

@router.message(F.text.in_(["📢 Broadcast", "📢 广播消息"]), IsBoshAdmin())
async def bc_start(message: types.Message, state: FSMContext, session: AsyncSession):
    lang = await get_user_lang_by_id(session, message.from_user.id)
    await state.set_state(BroadcastSt.text)
    await message.answer(get_text("bc_prompt", lang), reply_markup=cancel_kb(lang))


@router.message(BroadcastSt.text)
async def bc_preview(message: types.Message, state: FSMContext, session: AsyncSession):
    lang = await get_user_lang_by_id(session, message.from_user.id)
    menu_kb = bosh_admin_menu_kb(lang)
    if message.text in (get_text("cancel", "uz"), get_text("cancel", "zh")):
        await state.clear(); await message.answer("❌", reply_markup=menu_kb); return
    await state.update_data(text=message.text); await state.set_state(BroadcastSt.confirm)
    b = InlineKeyboardBuilder()
    b.button(text=get_text("confirm_btn", lang), callback_data="bc_yes")
    b.button(text=get_text("cancel_btn", lang), callback_data="bc_no")
    await message.answer(get_text("bc_preview", lang, message.text), reply_markup=b.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "bc_no")
async def bc_no(callback: types.CallbackQuery, state: FSMContext):
    await state.clear(); await callback.message.edit_text("❌ Bekor.")


@router.callback_query(F.data == "bc_yes", BroadcastSt.confirm)
async def bc_send(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    data = await state.get_data(); text = data["text"]; await state.clear()
    ids = await get_active_user_ids(session)
    await callback.message.edit_text(f"📤 Yuborilmoqda... 0/{len(ids)}")
    sent = failed = 0
    for i, uid in enumerate(ids, 1):
        try:
            await callback.bot.send_message(uid, text, parse_mode="HTML"); sent += 1
        except Exception: failed += 1
        if i % 25 == 0: await asyncio.sleep(1)
    await save_broadcast(session, callback.from_user.id, text, sent, failed)
    await callback.message.edit_text(get_text("bc_success", "uz", sent, failed), parse_mode="HTML")
