from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from config import settings
from utils.localization import get_text

def lang_selection_kb():
    b = InlineKeyboardBuilder()
    b.button(text="🇺🇿 O'zbekcha", callback_data="setlang:uz")
    b.button(text="🇨🇳 中文", callback_data="setlang:zh")
    b.adjust(2)
    return b.as_markup()

def main_menu_kb(lang: str = "uz"):
    kb = ReplyKeyboardBuilder()
    kb.button(text=get_text("order_button", lang), web_app=WebAppInfo(url=f"{settings.webapp_url}?lang={lang}"))
    kb.button(text=get_text("lang_button", lang))
    kb.adjust(1)
    return kb.as_markup(resize_keyboard=True)

def bosh_admin_menu_kb(lang: str = "uz"):
    kb = ReplyKeyboardBuilder()
    kb.button(text=get_text("stats", lang))
    kb.button(text=get_text("users", lang))
    kb.button(text=get_text("orders", lang))
    kb.button(text=get_text("products", lang))
    kb.button(text=get_text("publish_product", lang))
    kb.button(text=get_text("sheets", lang))
    kb.button(text=get_text("broadcast", lang))
    kb.button(text=get_text("back", lang))
    kb.adjust(2, 2, 2, 1, 1)
    return kb.as_markup(resize_keyboard=True)

def admin_menu_kb(lang: str = "uz"):
    # Alias for compatibility
    return bosh_admin_menu_kb(lang)

def sklad_menu_kb(lang: str = "uz"):
    kb = ReplyKeyboardBuilder()
    kb.button(text=get_text("sklad_add_product", lang))
    kb.button(text=get_text("back", lang))
    kb.adjust(1)
    return kb.as_markup(resize_keyboard=True)

def cancel_kb(lang: str = "uz"):
    kb = ReplyKeyboardBuilder()
    kb.button(text=get_text("cancel", lang))
    return kb.as_markup(resize_keyboard=True)

def webapp_inline_kb(lang: str = "uz"):
    b = InlineKeyboardBuilder()
    b.button(text=get_text("webapp_btn", lang), web_app=WebAppInfo(url=f"{settings.webapp_url}?lang={lang}"))
    return b.as_markup()

def order_action_kb(order_id: int, lang: str = "uz"):
    b = InlineKeyboardBuilder()
    b.button(text=get_text("confirm_btn", lang), callback_data=f"order_confirm:{order_id}")
    b.button(text=get_text("cancel_btn", lang),      callback_data=f"order_cancel:{order_id}")
    b.adjust(2)
    return b.as_markup()

def products_inline_kb(products, lang: str = "uz"):
    b = InlineKeyboardBuilder()
    for p in products:
        icon = "🖼" if p.photo_url else "📦"
        b.button(text=f"{icon} {p.name} — {int(p.price):,} so'm",
                 callback_data=f"buy:{p.id}")
    b.adjust(1)
    return b.as_markup()

def product_manage_kb(product_id: int, is_active: bool, lang: str = "uz", is_bosh_admin: bool = True):
    b = InlineKeyboardBuilder()
    b.button(text=get_text("edit_btn", lang),  callback_data=f"prod_edit:{product_id}")
    b.button(text=get_text("add_stock", lang), callback_data=f"prod_addstock:{product_id}")
    if is_bosh_admin:
        b.button(text=get_text("del_btn", lang),   callback_data=f"prod_del:{product_id}")
        b.button(text=(get_text("enable_btn", lang) if not is_active else get_text("disable_btn", lang)),
                 callback_data=f"prod_toggle:{product_id}")
        b.adjust(2, 2)
    else:
        b.adjust(2)
    return b.as_markup()
