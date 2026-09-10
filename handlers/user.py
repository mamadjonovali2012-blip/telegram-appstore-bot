from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from storage import list_apps, find_apps, get_app

router = Router()
APPS_PER_PAGE = 8


def _app_card(app):
    size_mb = round(app.size / (1024 * 1024), 2) if app.size else 0
    return (
        f"📦 <b>{app.name}</b>\n"
        f"📄 {app.description}\n"
        f"📎 {app.file_name} ({size_mb} MB)"
    )


def _paginate_keyboard(apps, page):
    total = len(apps)
    start = page * APPS_PER_PAGE
    end = start + APPS_PER_PAGE
    page_apps = apps[start:end]
    kb = InlineKeyboardBuilder()
    for a in page_apps:
        kb.button(text=a.name, callback_data=f"app_{a.id}")
    kb.adjust(2)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"page_{page - 1}"))
    if end < total:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"page_{page + 1}"))
    if nav:
        kb.row(*nav)
    return kb.as_markup()


@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "📱 <b>AppStore Bot</b>\n\n"
        "Доступные команды:\n"
        "/apps — список всех приложений\n"
        "/search <текст> — поиск по названию или описанию\n"
        "/upload — загрузить приложение (только админ)\n"
        "/delete — удалить приложение (только админ)",
    )


@router.message(Command("apps"))
async def cmd_apps(message: Message):
    apps = list_apps()
    if not apps:
        await message.answer("Пока нет ни одного приложения.")
        return
    await message.answer(
        "📱 <b>Список приложений:</b>",
        reply_markup=_paginate_keyboard(apps, 0),
    )


@router.callback_query(F.data.startswith("page_"))
async def on_page(cq: CallbackQuery):
    page = int(cq.data.split("_")[1])
    apps = list_apps()
    await cq.message.edit_text(
        "📱 <b>Список приложений:</b>",
        reply_markup=_paginate_keyboard(apps, page),
    )
    await cq.answer()


@router.callback_query(F.data.startswith("app_"))
async def on_app(cq: CallbackQuery):
    app_id = cq.data.split("_", 1)[1]
    app = get_app(app_id)
    if not app:
        await cq.answer("Приложение не найдено.", show_alert=True)
        return
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📥 Скачать", callback_data=f"dl_{app.id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_list")],
        ]
    )
    await cq.message.edit_text(_app_card(app), reply_markup=kb)
    await cq.answer()


@router.callback_query(F.data == "back_to_list")
async def on_back(cq: CallbackQuery):
    apps = list_apps()
    await cq.message.edit_text(
        "📱 <b>Список приложений:</b>",
        reply_markup=_paginate_keyboard(apps, 0),
    )
    await cq.answer()


@router.callback_query(F.data.startswith("dl_"))
async def on_download(cq: CallbackQuery):
    app_id = cq.data.split("_", 1)[1]
    app = get_app(app_id)
    if not app:
        await cq.answer("Приложение не найдено.", show_alert=True)
        return
    await cq.message.answer_document(app.file_id, caption=f"📦 {app.name}")
    await cq.answer()


@router.message(Command("search"))
async def cmd_search(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Укажите запрос: /search <текст>")
        return
    query = parts[1].strip()
    results = find_apps(query)
    if not results:
        await message.answer(f"Ничего не найдено по запросу «{query}».")
        return
    await message.answer(
        f"🔍 Результаты по запросу «{query}»:",
        reply_markup=_paginate_keyboard(results, 0),
    )