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

def to_utc8(dt: datetime) -> datetime:
    """Convert a naive UTC datetime from database to UTC-8 timezone."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone(timedelta(hours=-8)))

def get_utc8_now() -> datetime:
    """Get the current time in UTC-8 timezone."""
    return datetime.now(timezone(timedelta(hours=-8)))

async def sync_to_sheets() -> str:
    """
    Sync stock level and monthly sales data to Google Sheets in UTC-8 timezone.
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

        # 2. Perform UTC-8 calculations
        now_utc8 = get_utc8_now()
        current_year = now_utc8.year
        current_month = now_utc8.month
        # Start of current month in UTC-8
        first_day_current_month = datetime(current_year, current_month, 1, 0, 0, 0, tzinfo=timezone(timedelta(hours=-8)))

        rows = []
        for p in products:
            pid = p.id
            name = p.name

            # Calculate total additions before current month
            additions_before = sum(
                t.quantity for t in txs
                if t.product_id == pid and to_utc8(t.created_at) < first_day_current_month
            )
            # Calculate total confirmed sales before current month
            sales_before = sum(
                o.quantity for o in orders
                if o.product_id == pid and to_utc8(o.created_at) < first_day_current_month
            )
            # Previous month remaining stock
            prev_month_stock = max(0, additions_before - sales_before)

            # This month's stock additions (production)
            this_month_additions = sum(
                t.quantity for t in txs
                if t.product_id == pid and to_utc8(t.created_at) >= first_day_current_month
            )

            # This month's sales quantity
            this_month_sales = sum(
                o.quantity for o in orders
                if o.product_id == pid and to_utc8(o.created_at) >= first_day_current_month
            )

            # This month's sales revenue
            this_month_revenue = sum(
                o.price for o in orders
                if o.product_id == pid and to_utc8(o.created_at) >= first_day_current_month
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
            time_str = now_utc8.strftime("%Y-%m-%d %H:%M:%S")
            month_str = now_utc8.strftime("%B %Y")
            header_info = [
                ["Hisobot davri (Reporting Period):", month_str, "", "Vaqt zonasi (Timezone):", "UTC-8"],
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
            worksheet.update("A1", all_data)
            return sheet.url

        sheet_url = await loop.run_in_executor(None, update_sheets_worker)
        logger.info(f"Google Sheets inventory report successfully updated. URL: {sheet_url}")
        return sheet_url

    except Exception as e:
        logger.error(f"Failed to sync inventory report to Google Sheets: {e}", exc_info=True)
        raise e
