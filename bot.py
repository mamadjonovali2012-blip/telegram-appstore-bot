import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession

from aiohttp import web

from config import BOT_TOKEN, PROXY, ADMIN_IDS, WEBAPP_URL
from backup import restore_backup, backup_loop
from handlers import admin, common, user
from admin_api import setup_admin_api

logging.basicConfig(level=logging.INFO)

PORT = int(os.getenv("PORT", 10000))


async def health(request):
    return web.Response(text="ok")


async def version(request):
    commit = os.getenv("RENDER_GIT_COMMIT", "unknown")
    return web.Response(text=f"commit={commit}")


async def set_commands(bot: Bot):
    default_commands = [
        types.BotCommand(command="start", description="🏠 Главное меню"),
        types.BotCommand(command="menu", description="📋 Меню"),
        types.BotCommand(command="search", description="🔍 Поиск приложений"),
        types.BotCommand(command="cancel", description="❌ Отменить действие"),
    ]
    admin_commands = default_commands + [
        types.BotCommand(command="upload", description="📤 Загрузить приложение"),
        types.BotCommand(command="edit", description="✏️ Редактировать приложение"),
        types.BotCommand(command="delete", description="🗑 Удалить приложение"),
        types.BotCommand(command="stats", description="📊 Статистика"),
        types.BotCommand(command="broadcast", description="📢 Рассылка"),
        types.BotCommand(command="backup", description="💾 Сохранить данные"),
        types.BotCommand(command="restore", description="📥 Восстановить данные"),
    ]
    await bot.set_my_commands(default_commands)
    for admin_id in ADMIN_IDS:
        try:
            await bot.set_my_commands(
                admin_commands,
                scope=types.BotCommandScopeChat(chat_id=admin_id),
            )
            await bot.set_chat_menu_button(
                chat_id=admin_id,
                menu_button=types.MenuButtonWebApp(
                    text="⚙️ Панель админа",
                    web_app=types.WebAppInfo(url=WEBAPP_URL),
                ),
            )
        except Exception as e:
            logging.warning("Failed to set admin commands for %s: %s", admin_id, e)


async def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN не задан в .env")

    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/version", version)
    setup_admin_api(app)

    @web.middleware
    async def cors_middleware(request, handler):
        if request.path.startswith("/admin-api/"):
            if request.method == "OPTIONS":
                resp = web.Response(status=204)
            else:
                resp = await handler(request)
            resp.headers["Access-Control-Allow-Origin"] = "*"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
            return resp
        return await handler(request)

    app.middlewares.append(cors_middleware)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logging.info("Health server listening on 0.0.0.0:%d", PORT)

    asyncio.create_task(_startup_backup())

    session = AiohttpSession(proxy=PROXY) if PROXY else None
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML"),
        session=session,
    )
    dp = Dispatcher()

    @dp.errors()
    async def error_handler(event: types.ErrorEvent):
        logging.error("Update error: %s", event.exception)

    dp.include_router(common.router)
    dp.include_router(admin.router)
    dp.include_router(user.router)

    await set_commands(bot)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


async def _startup_backup():
    try:
        await asyncio.wait_for(restore_backup(), timeout=30)
    except asyncio.TimeoutError:
        logging.warning("Backup restore timed out, continuing without it")
    except Exception as e:
        logging.error("Backup restore failed: %s", e)
    asyncio.create_task(backup_loop(300))


if __name__ == "__main__":
    asyncio.run(main())