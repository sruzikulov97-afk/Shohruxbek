"""
utils/sheets.py
Google Sheets integration module.
"""
import logging
import json
import asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy import select

import gspread
from google.oauth2.service_account import Credentials

from config import settings
from database.models import AsyncSessionLocal, Product, StockTransaction, Order

logger = logging.getLogger(__name__)

# Scopes for Google Sheets and Drive access
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def to_tashkent(dt: datetime) -> datetime:
    """Convert a naive UTC datetime from database to Tashkent timezone (UTC+5)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone(timedelta(hours=5)))

def get_tashkent_now() -> datetime:
    """Get the current time in Tashkent timezone (UTC+5)."""
    return datetime.now(timezone(timedelta(hours=5)))

async def sync_to_sheets() -> str:
    """
    Sync stock level and monthly sales data to Google Sheets in Tashkent timezone (UTC+5).
    Returns:
        str: The Google Sheets URL if sync succeeded, empty string otherwise.
    """
    # Check if Google Sheets settings are configured
    if not settings.google_sheet_id or not (settings.google_service_account_json or settings.google_service_account_file):
        logger.warning("Google Sheets sync triggered but credentials are not configured in settings.")
        return ""

    try:
        # 1. Fetch all required data from DB
        async with AsyncSessionLocal() as session:
            products = (await session.execute(select(Product))).scalars().all()
            txs = (await session.execute(select(StockTransaction))).scalars().all()
            orders = (await session.execute(select(Order).where(Order.status == "confirmed"))).scalars().all()

        # 2. Perform Tashkent (UTC+5) calculations
        now_tashkent = get_tashkent_now()
        current_year = now_tashkent.year
        current_month = now_tashkent.month
        # Start of current month in Tashkent
        first_day_current_month = datetime(current_year, current_month, 1, 0, 0, 0, tzinfo=timezone(timedelta(hours=5)))

        rows = []
        for p in products:
            pid = p.id
            name = p.name

            # Calculate total additions before current month
            additions_before = sum(
                t.quantity for t in txs
                if t.product_id == pid and to_tashkent(t.created_at) < first_day_current_month
            )
            # Calculate total confirmed sales before current month
            sales_before = sum(
                o.quantity for o in orders
                if o.product_id == pid and to_tashkent(o.created_at) < first_day_current_month
            )
            # Previous month remaining stock
            prev_month_stock = max(0, additions_before - sales_before)

            # This month's stock additions (production)
            this_month_additions = sum(
                t.quantity for t in txs
                if t.product_id == pid and to_tashkent(t.created_at) >= first_day_current_month
            )

            # This month's sales quantity
            this_month_sales = sum(
                o.quantity for o in orders
                if o.product_id == pid and to_tashkent(o.created_at) >= first_day_current_month
            )

            # This month's sales revenue
            this_month_revenue = sum(
                o.price for o in orders
                if o.product_id == pid and to_tashkent(o.created_at) >= first_day_current_month
            )

            current_balance = p.stock or 0

            rows.append([
                pid,
                name,
                prev_month_stock,
                this_month_additions,
                this_month_sales,
                current_balance,
                this_month_revenue
            ])

        # Sort rows by product ID
        rows.sort(key=lambda x: x[0])

        # 3. Write data to Google Sheets worksheet (run in executor to keep it non-blocking)
        loop = asyncio.get_running_loop()

        def update_sheets_worker():
            # Load credentials
            if settings.google_service_account_json:
                try:
                    info = json.loads(settings.google_service_account_json)
                    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
                except Exception as e:
                    logger.error(f"Failed to load service account credentials from raw JSON: {e}")
                    raise e
            else:
                try:
                    creds = Credentials.from_service_account_file(settings.google_service_account_file, scopes=SCOPES)
                except Exception as e:
                    logger.error(f"Failed to load service account credentials from file: {e}")
                    raise e

            client = gspread.authorize(creds)
            sheet = client.open_by_key(settings.google_sheet_id)

            # Access or create the specific worksheet for reports
            try:
                worksheet = sheet.worksheet("Sklad_Hisobot")
            except gspread.exceptions.WorksheetNotFound:
                worksheet = sheet.add_worksheet(title="Sklad_Hisobot", rows=100, cols=10)

            # Clear existing content
            worksheet.clear()

            # Set up the report layout
            time_str = now_tashkent.strftime("%Y-%m-%d %H:%M:%S")
            month_str = now_tashkent.strftime("%B %Y")
            header_info = [
                ["Hisobot davri (Reporting Period):", month_str, "", "Vaqt zonasi (Timezone):", "UTC+5 (Tashkent)"],
                ["Yangilangan vaqt (Last Updated):", time_str, "", "", ""],
                [] # Blank row for spacing
            ]

            table_headers = [
                "Mahsulot ID",
                "Mahsulot nomi",
                "O'tgan oydan qoldiq (dona)",
                "Shu oy ishlab chiqarish (dona)",
                "Shu oy sotuv (dona)",
                "Joriy qoldiq (dona)",
                "Shu oy savdo miqdori (so'm)"
            ]

            all_data = header_info + [table_headers] + rows
            try:
                worksheet.update(values=all_data, range_name="A1")
            except Exception:
                worksheet.update("A1", all_data)

            # Apply cell and column formatting to make the sheet look clean and professional
            try:
                # 1. Bold the top info metadata
                worksheet.format("A1:E2", {
                    "textFormat": {"bold": True},
                    "horizontalAlignment": "LEFT"
                })

                # 2. Format Table Headers (Row 4) with a sleek dark Navy theme
                worksheet.format("A4:G4", {
                    "backgroundColor": {
                        "red": 0.08,
                        "green": 0.18,
                        "blue": 0.36
                    },
                    "textFormat": {
                        "bold": True,
                        "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                        "fontSize": 11
                    },
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE"
                })

                # 3. Format Data Rows (Row 5 onwards)
                max_row = len(rows) + 4
                if max_row >= 5:
                    worksheet.format(f"A5:A{max_row}", {"horizontalAlignment": "CENTER"})
                    worksheet.format(f"B5:B{max_row}", {"horizontalAlignment": "LEFT"})
                    worksheet.format(f"C5:F{max_row}", {"horizontalAlignment": "CENTER"})
                    
                    # Format revenue column with thousands separator and "so'm" suffix
                    worksheet.format(f"G5:G{max_row}", {
                        "horizontalAlignment": "RIGHT",
                        "numberFormat": {
                            "type": "NUMBER",
                            "pattern": "#,##0 \"so'm\""
                        }
                    })

                # 4. Auto-resize columns to fit content perfectly
                worksheet.columns_auto_resize(0, 7)
            except Exception as fe:
                logger.warning(f"Non-critical Sheets formatting error: {fe}")

            return sheet.url

        sheet_url = await loop.run_in_executor(None, update_sheets_worker)
        logger.info(f"Google Sheets inventory report successfully updated. URL: {sheet_url}")

        # Construct and send the report messages to the group and admins
        try:
            from aiogram import Bot
            from aiogram.client.default import DefaultBotProperties
            from aiogram.enums import ParseMode

            # Format product stock list
            prod_lines = []
            total_additions = 0
            total_sales = 0
            total_balance = 0
            total_revenue = 0

            for r in rows:
                # r: [pid, name, prev_month_stock, this_month_additions, this_month_sales, current_balance, this_month_revenue]
                prod_lines.append(f"  • {r[1]}: <b>{r[5]}</b> ta")
                total_additions += r[3]
                total_sales += r[4]
                total_balance += r[5]
                total_revenue += r[6]

            prod_lines_text = "\n".join(prod_lines[:25])
            if len(rows) > 25:
                prod_lines_text += "\n  • ..."

            time_str = now_tashkent.strftime("%Y-%m-%d %H:%M:%S")
            month_str = now_tashkent.strftime("%B %Y")

            report_msg = (
                f"📊 <b>GOOGLE SHEETS HISOBOTI YANGILANDI</b>\n"
                f"📅 Davr: <b>{month_str}</b>\n"
                f"🕒 Yangilangan vaqt: <code>{time_str} (UTC+5)</code>\n\n"
                f"📈 <b>Umumiy statistika:</b>\n"
                f"• Mahsulot turlari: {len(products)} ta\n"
                f"• Shu oy ishlab chiqarildi: <b>{total_additions}</b> ta\n"
                f"• Shu oy sotildi: <b>{total_sales}</b> ta\n"
                f"• Sklad joriy qoldig'i: <b>{total_balance}</b> ta\n"
                f"• Shu oy jami tushum: <b>{int(total_revenue):,} so'm</b>\n\n"
                f"📋 <b>Sklad qoldiqlari:</b>\n{prod_lines_text}\n\n"
                f"🔗 Google Sheets havolasi:\n{sheet_url}"
            )

            # 1. Send report to Group if configured
            if settings.report_group_id:
                try:
                    temp_bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
                    chat_id = settings.report_group_id.strip()
                    if chat_id.replace('-', '').replace('+', '').isdigit():
                        chat_id = int(chat_id)
                    await temp_bot.send_message(chat_id, report_msg)
                    await temp_bot.session.close()
                    logger.info(f"Report message successfully sent to group {settings.report_group_id}")
                except Exception as ge:
                    logger.error(f"Failed to send report to group: {ge}")

            # 2. Send report to Bosh Admins (Group owner / creator)
            for admin_id in settings.admin_list:
                try:
                    temp_bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
                    await temp_bot.send_message(admin_id, report_msg)
                    await temp_bot.session.close()
                    logger.info(f"Report message successfully sent to admin {admin_id}")
                except Exception as ae:
                    logger.error(f"Failed to send report to admin {admin_id}: {ae}")

        except Exception as msg_err:
            logger.error(f"Failed to construct or send report messages: {msg_err}")

        return sheet_url

    except Exception as e:
        logger.error(f"Failed to sync inventory report to Google Sheets: {e}", exc_info=True)
        raise e
