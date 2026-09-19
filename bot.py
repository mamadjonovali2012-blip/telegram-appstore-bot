import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession

from aiohttp import web

from config import BOT_TOKEN, PROXY
from backup import restore_backup, backup_loop
from handlers import admin, user

logging.basicConfig(level=logging.INFO)

PORT = int(os.getenv("PORT", 10000))


async def health(request):
    return web.Response(text="ok")


async def set_commands(bot: Bot):
    await bot.set_my_commands([
        types.BotCommand(command="start", description="🏠 Главное меню"),
        types.BotCommand(command="menu", description="📋 Меню"),
        types.BotCommand(command="search", description="🔍 Поиск приложений"),
    ])


async def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN не задан в .env")

    app = web.Application()
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logging.info("Health server listening on 0.0.0.0:%d", PORT)

    await restore_backup()
    asyncio.create_task(backup_loop(300))

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

    dp.include_router(admin.router)
    dp.include_router(user.router)

    await set_commands(bot)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())