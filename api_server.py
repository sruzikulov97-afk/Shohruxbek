"""
api_server.py — Full REST API for bot, webapp, and admin panel
"""
from aiohttp import web
from database.models import AsyncSessionLocal, Product, User, Order, BroadcastLog
from database.crud import (
    get_all_products, get_product, create_product, update_product,
    delete_product, toggle_product,
    get_all_users, get_user_count, get_active_user_ids,
    ban_user, unban_user,
    get_orders, get_order_count, get_total_revenue, update_order_status,
    get_broadcasts, save_broadcast,
)
from config import settings
from sqlalchemy import select, func
import json, os


# ── Helpers ────────────────────────────────────────────────────────────────────

def cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
    }

def json_response(data, status=200):
    return web.Response(
        text=json.dumps(data, ensure_ascii=False, default=str),
        content_type="application/json",
        headers=cors_headers(),
        status=status,
    )

def error_response(msg, status=400):
    return json_response({"error": msg}, status=status)

async def options_handler(request):
    return web.Response(headers=cors_headers())


# ── Login ──────────────────────────────────────────────────────────────────────

async def api_login(request):
    try:
        body = await request.json()
        password = body.get("password", "")
        ok = password == settings.admin_password
        return json_response({"ok": ok})
    except Exception as e:
        return error_response(str(e))


# ── Stats ──────────────────────────────────────────────────────────────────────

async def api_stats(request):
    async with AsyncSessionLocal() as session:
        user_count = await get_user_count(session)
        order_count = await get_order_count(session)
        revenue = await get_total_revenue(session)
        products = await get_all_products(session)
        active_products = sum(1 for p in products if p.is_active)
        orders = await get_orders(session, limit=100000)
        pending = sum(1 for o in orders if o.status == "pending")
        return json_response({
            "user_count": user_count,
            "product_count": len(products),
            "order_count": order_count,
            "revenue": revenue,
            "pending_orders": pending,
            "active_products": active_products,
        })


# ── Products ───────────────────────────────────────────────────────────────────

async def api_get_products(request):
    active_only = request.query.get("active_only", "false").lower() == "true"
    async with AsyncSessionLocal() as session:
        products = await get_all_products(session, only_active=active_only)
        data = [
            {
                "id": p.id, "name": p.name, "price": p.price,
                "category": p.category or "", "photo_url": p.photo_url or "",
                "description": p.description or "", "is_active": p.is_active,
                "created_at": str(p.created_at) if p.created_at else "",
                "updated_at": str(p.updated_at) if p.updated_at else "",
            }
            for p in products
        ]
    return json_response(data)

async def api_create_product(request):
    try:
        body = await request.json()
        async with AsyncSessionLocal() as session:
            p = await create_product(
                session,
                name=body["name"],
                price=float(body["price"]),
                photo_url=body.get("photo_url"),
                category=body.get("category", "Asosiy"),
                description=body.get("description", ""),
            )
            return json_response({
                "id": p.id, "name": p.name, "price": p.price,
                "category": p.category, "photo_url": p.photo_url or "",
                "description": p.description or "", "is_active": p.is_active,
            }, status=201)
    except Exception as e:
        return error_response(str(e))

async def api_update_product(request):
    try:
        pid = int(request.match_info["id"])
        body = await request.json()
        kwargs = {}
        for key in ["name", "price", "photo_url", "category", "description", "is_active"]:
            if key in body:
                val = body[key]
                if key == "price":
                    val = float(val)
                kwargs[key] = val
        async with AsyncSessionLocal() as session:
            ok = await update_product(session, pid, **kwargs)
            if ok:
                p = await get_product(session, pid)
                return json_response({
                    "id": p.id, "name": p.name, "price": p.price,
                    "category": p.category, "photo_url": p.photo_url or "",
                    "description": p.description or "", "is_active": p.is_active,
                })
            return error_response("Topilmadi", 404)
    except Exception as e:
        return error_response(str(e))

async def api_delete_product(request):
    try:
        pid = int(request.match_info["id"])
        async with AsyncSessionLocal() as session:
            ok = await delete_product(session, pid)
            return json_response({"ok": ok})
    except Exception as e:
        return error_response(str(e))

async def api_toggle_product(request):
    try:
        pid = int(request.match_info["id"])
        async with AsyncSessionLocal() as session:
            new_state = await toggle_product(session, pid)
            if new_state is None:
                return error_response("Topilmadi", 404)
            return json_response({"is_active": new_state})
    except Exception as e:
        return error_response(str(e))


# ── Users ──────────────────────────────────────────────────────────────────────

async def api_get_users(request):
    async with AsyncSessionLocal() as session:
        users = await get_all_users(session, limit=500)
        data = [
            {
                "id": u.id, "telegram_id": u.telegram_id,
                "username": u.username or "", "first_name": u.first_name or "",
                "last_name": u.last_name or "", "full_name": u.full_name,
                "language_code": u.language_code or "",
                "is_banned": u.is_banned,
                "created_at": str(u.created_at) if u.created_at else "",
                "last_active": str(u.last_active) if u.last_active else "",
            }
            for u in users
        ]
    return json_response(data)

async def api_user_count(request):
    async with AsyncSessionLocal() as session:
        count = await get_user_count(session)
        return json_response({"count": count})

async def api_ban_user(request):
    try:
        tid = int(request.match_info["tid"])
        async with AsyncSessionLocal() as session:
            ok = await ban_user(session, tid)
            return json_response({"ok": ok})
    except Exception as e:
        return error_response(str(e))

async def api_unban_user(request):
    try:
        tid = int(request.match_info["tid"])
        async with AsyncSessionLocal() as session:
            ok = await unban_user(session, tid)
            return json_response({"ok": ok})
    except Exception as e:
        return error_response(str(e))


# ── Orders ─────────────────────────────────────────────────────────────────────

async def api_get_orders(request):
    status_filter = request.query.get("status")
    async with AsyncSessionLocal() as session:
        orders = await get_orders(session, limit=500)
        data = [
            {
                "id": o.id, "user_id": o.user_id,
                "product": o.product or "", "product_id": o.product_id,
                "quantity": o.quantity, "price": o.price,
                "status": o.status or "pending",
                "note": o.note or "",
                "created_at": str(o.created_at) if o.created_at else "",
            }
            for o in orders
            if not status_filter or o.status == status_filter
        ]
    return json_response(data)

async def api_update_order_status(request):
    try:
        oid = int(request.match_info["id"])
        body = await request.json()
        status = body.get("status", "")
        if status not in ("confirmed", "cancelled", "pending"):
            return error_response("Noto'g'ri status")
        async with AsyncSessionLocal() as session:
            ok = await update_order_status(session, oid, status)
            return json_response({"ok": ok})
    except Exception as e:
        return error_response(str(e))


# ── Broadcasts ─────────────────────────────────────────────────────────────────

async def api_get_broadcasts(request):
    async with AsyncSessionLocal() as session:
        bcs = await get_broadcasts(session, limit=100)
        data = [
            {
                "id": b.id, "admin_id": b.admin_id,
                "message_text": b.message_text,
                "total_sent": b.total_sent, "total_failed": b.total_failed,
                "created_at": str(b.created_at) if b.created_at else "",
            }
            for b in bcs
        ]
    return json_response(data)

async def api_save_broadcast(request):
    try:
        body = await request.json()
        async with AsyncSessionLocal() as session:
            log = await save_broadcast(
                session,
                admin_id=int(body.get("admin_id", 0)),
                text=body.get("text", ""),
                sent=int(body.get("sent", 0)),
                failed=int(body.get("failed", 0)),
            )
            return json_response({"id": log.id}, status=201)
    except Exception as e:
        return error_response(str(e))


# ── Debug Info ────────────────────────────────────────────────────────────────
async def api_debug(request):
    try:
        from aiogram import Bot
        token = settings.bot_token
        masked_token = f"{token[:8]}...{token[-5:]}" if token and len(token) > 15 else "None"
        
        bot_info = "None"
        try:
            temp_bot = Bot(token=token)
            me = await temp_bot.get_me()
            bot_info = f"@{me.username} (ID: {me.id})"
            await temp_bot.session.close()
        except Exception as e:
            bot_info = f"Error: {str(e)}"

        return json_response({
            "bot_token_masked": masked_token,
            "bot_info": bot_info,
            "webapp_url": settings.webapp_url,
            "admin_ids": settings.admin_ids,
            "database_url": settings.database_url,
            "env_port": os.environ.get("PORT", "None")
        })
    except Exception as e:
        return error_response(str(e))


# ── Static files ───────────────────────────────────────────────────────────────

async def serve_webapp(request):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webapp", "index.html")
    if os.path.exists(path):
        return web.FileResponse(path)
    return web.Response(text="Not found", status=404)

async def serve_admin(request):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "admin", "index.html")
    if os.path.exists(path):
        return web.FileResponse(path)
    return web.Response(text="Not found", status=404)


# ── App factory ────────────────────────────────────────────────────────────────

def create_app():
    app = web.Application()

    # CORS preflight
    app.router.add_route("OPTIONS", "/api/{tail:.*}", options_handler)

    # Auth
    app.router.add_post("/api/login", api_login)

    # Stats
    app.router.add_get("/api/stats", api_stats)
    app.router.add_get("/api/debug", api_debug)

    # Products
    app.router.add_get("/api/products", api_get_products)
    app.router.add_post("/api/products", api_create_product)
    app.router.add_put("/api/products/{id}", api_update_product)
    app.router.add_delete("/api/products/{id}", api_delete_product)
    app.router.add_post("/api/products/{id}/toggle", api_toggle_product)

    # Users
    app.router.add_get("/api/users", api_get_users)
    app.router.add_get("/api/users/count", api_user_count)
    app.router.add_post("/api/users/{tid}/ban", api_ban_user)
    app.router.add_post("/api/users/{tid}/unban", api_unban_user)

    # Orders
    app.router.add_get("/api/orders", api_get_orders)
    app.router.add_post("/api/orders/{id}/status", api_update_order_status)

    # Broadcasts
    app.router.add_get("/api/broadcasts", api_get_broadcasts)
    app.router.add_post("/api/broadcasts", api_save_broadcast)

    # Static pages
    app.router.add_get("/webapp", serve_webapp)
    app.router.add_get("/webapp/", serve_webapp)
    app.router.add_get("/admin", serve_admin)
    app.router.add_get("/admin/", serve_admin)
    app.router.add_get("/", serve_webapp)

    return app
