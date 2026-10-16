"""HTTP API для мини-приложения «Панель админа».

Авторизация: Telegram WebApp (initData) -> проверка подписи и admin_id.
Изменяющие действия (добавить/скрыть/удалить) доступны только админу.
"""
import hmac
import hashlib
import json
import logging
import urllib.parse

from aiohttp import web

from config import BOT_TOKEN, ADMIN_IDS
import db

logger = logging.getLogger(__name__)


def _parse_init_data(init_data: str):
    """Разобрать initData в dict + вернуть data_check_string."""
    pairs = urllib.parse.parse_qsl(init_data, keep_blank_values=True)
    if not pairs:
        return None, None
    d = dict(pairs)
    # Дубликаты ключей не ожидаются; data_check_string строится из всех пар.
    sorted_pairs = sorted((k, v) for k, v in pairs if k != "hash")
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted_pairs)
    return d, data_check_string


def validate_init_data(init_data: str):
    """Вернуть dict с инициализацией, если подпись валидна, иначе None."""
    try:
        d, dcs = _parse_init_data(init_data)
        if d is None or "hash" not in d:
            return None
        secret_key = hashlib.sha256(BOT_TOKEN.encode()).digest()
        calc = hmac.new(secret_key, dcs.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, d["hash"]):
            return None
        return d
    except Exception as e:
        logger.warning("initData validation error: %s", e)
        return None


def auth_required(handler):
    async def wrapper(request):
        auth = request.headers.get("Authorization", "")
        init_data = auth[len("initData "):] if auth.startswith("initData ") else ""
        if not init_data:
            init_data = request.query.get("init_data", "")
        data = validate_init_data(init_data)
        if not data:
            return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)
        try:
            user = json.loads(data.get("user", "{}"))
            user_id = int(user.get("id", 0))
        except Exception:
            user_id = 0
        if user_id not in ADMIN_IDS:
            return web.json_response({"ok": False, "error": "Forbidden"}, status=403)
        request["tg_user_id"] = user_id
        return await handler(request)

    return wrapper


def _public_app(app):
    return {
        "id": app["id"],
        "name": app["name"],
        "description": app["description"],
        "category": app["category"],
        "icon_emoji": app["icon_emoji"],
        "version": app["version"],
        "file_name": app["file_name"],
        "size": app["size"],
        "downloads": app["downloads"],
        "hidden": bool(app.get("hidden")),
        "is_private": bool(app.get("is_private")),
    }


async def _app_body(request):
    try:
        return json.loads(await request.text())
    except Exception:
        return {}


async def api_list(request):
    apps = db.list_apps(only_public=False, per_page=10000)
    return web.json_response({"ok": True, "apps": [_public_app(a) for a in apps]})


async def api_set_hidden(request):
    body = await _app_body(request)
    app_id = body.get("id")
    hidden = bool(body.get("hidden"))
    app = db.get_app(app_id)
    if not app:
        return web.json_response({"ok": False, "error": "Not found"}, status=404)
    db.set_hidden(app_id, hidden)
    return web.json_response({"ok": True})


async def api_toggle_hidden(request):
    body = await _app_body(request)
    app_id = body.get("id")
    app = db.get_app(app_id)
    if not app:
        return web.json_response({"ok": False, "error": "Not found"}, status=404)
    new_hidden = not app.get("hidden")
    db.set_hidden(app_id, new_hidden)
    return web.json_response({"ok": True, "hidden": new_hidden})


async def api_delete(request):
    body = await _app_body(request)
    app_id = body.get("id")
    if not db.get_app(app_id):
        return web.json_response({"ok": False, "error": "Not found"}, status=404)
    db.remove_app(app_id)
    return web.json_response({"ok": True})


async def api_stats(request):
    total_apps, total_downloads, total_users, top = db.get_stats()
    return web.json_response({
        "ok": True,
        "stats": {
            "apps": total_apps,
            "downloads": total_downloads,
            "users": total_users,
            "top": [_public_app(a) for a in top],
        },
    })


def setup_admin_api(app: web.Application):
    app.router.add_get("/admin-api/list", auth_required(api_list))
    app.router.add_post("/admin-api/hidden", auth_required(api_set_hidden))
    app.router.add_post("/admin-api/toggle", auth_required(api_toggle_hidden))
    app.router.add_post("/admin-api/delete", auth_required(api_delete))
    app.router.add_get("/admin-api/stats", auth_required(api_stats))