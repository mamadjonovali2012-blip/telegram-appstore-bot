import html
import asyncio
import logging

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, CopyTextButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_IDS
from db import (
    add_app, remove_app, get_app, update_app, get_stats, list_apps, count_apps,
    all_user_ids, text, CATEGORIES, cat_name, size_mb,
)

router = Router()

ADMIN_PER_PAGE = 5


class UploadState(StatesGroup):
    name = State()
    description = State()
    category = State()
    icon = State()
    version = State()
    file = State()


class BroadcastState(StatesGroup):
    text = State()


def is_admin(user_id):
    return user_id in ADMIN_IDS


@router.message(Command("upload"))
async def cmd_upload(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer(text("admin_only"))
        return
    await state.set_state(UploadState.name)
    await message.answer(text("upload_name"))


@router.message(UploadState.name)
async def upload_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(UploadState.description)
    await message.answer(text("upload_desc"))


@router.message(UploadState.description)
async def upload_desc(message: Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    kb = InlineKeyboardBuilder()
    for key, emoji in CATEGORIES.items():
        kb.button(text=f"{emoji} {key}", callback_data=f"cat_{key}")
    kb.adjust(2)
    await state.set_state(UploadState.category)
    await message.answer(text("upload_cat"), reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("cat_"), UploadState.category)
async def upload_cat(cq: CallbackQuery, state: FSMContext):
    cat = cq.data.split("_", 1)[1]
    await state.update_data(category=cat)
    await state.set_state(UploadState.icon)
    await cq.message.edit_text(text("upload_icon"))
    await cq.answer()


@router.message(UploadState.icon)
async def upload_icon(message: Message, state: FSMContext):
    if message.text and message.text.strip() == "/skip":
        await state.update_data(icon="")
    elif message.text and len(message.text.strip()) <= 2:
        await state.update_data(icon=message.text.strip())
    else:
        await message.answer("Отправьте один эмодзи или /skip")
        return
    await state.set_state(UploadState.version)
    await message.answer(text("upload_ver"))


@router.message(UploadState.version)
async def upload_version(message: Message, state: FSMContext):
    await state.update_data(version=message.text.strip() or "1.0")
    await state.set_state(UploadState.file)
    await message.answer(text("upload_file"))


@router.message(UploadState.file, F.document)
async def upload_file(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    doc = message.document
    icon = data.get("icon") or CATEGORIES.get(data.get("category", "other"), "📦")
    app_id = add_app(
        name=data["name"],
        description=data.get("description", ""),
        category=data.get("category", "other"),
        icon_emoji=icon,
        version=data.get("version", "1.0"),
        file_id=doc.file_id,
        file_name=doc.file_name,
        size=doc.file_size,
        added_by=message.from_user.id,
    )
    await state.clear()
    await message.answer(text("upload_done", name=html.escape(data["name"]), id=app_id))


@router.message(UploadState.file)
async def upload_file_invalid(message: Message):
    await message.answer(text("upload_no_file"))


@router.message(Command("delete"))
async def cmd_delete(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer(text("admin_only"))
        return
    total = count_apps()
    if total == 0:
        await message.answer(text("no_apps"))
        return
    apps = list_apps(page=0, per_page=ADMIN_PER_PAGE)
    await message.answer(
        f"🗑 <b>Удаление приложений</b> — стр. 1/{max(1, (total + ADMIN_PER_PAGE - 1) // ADMIN_PER_PAGE)}",
        reply_markup=_delete_keyboard(apps, 0, total),
    )


def _delete_keyboard(apps, page, total):
    kb = InlineKeyboardBuilder()
    for a in apps:
        label = f"{a['icon_emoji']} {a['name']}"
        kb.row(
            InlineKeyboardButton(text=label, callback_data=f"delinfo_{a['id']}"),
            InlineKeyboardButton(text="🗑", callback_data=f"delconf_{a['id']}"),
        )
    total_pages = max(1, (total + ADMIN_PER_PAGE - 1) // ADMIN_PER_PAGE)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"delpage_{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"delpage_{page + 1}"))
    if nav:
        kb.row(*nav)
    kb.row(InlineKeyboardButton(text="🚫 Закрыть", callback_data="delclose"))
    return kb.as_markup()


@router.callback_query(F.data.startswith("delpage_"))
async def delete_page(cq: CallbackQuery):
    if not is_admin(cq.from_user.id):
        return
    page = int(cq.data.split("_", 1)[1])
    total = count_apps()
    apps = list_apps(page=page, per_page=ADMIN_PER_PAGE)
    total_pages = max(1, (total + ADMIN_PER_PAGE - 1) // ADMIN_PER_PAGE)
    await cq.message.edit_text(
        f"🗑 <b>Удаление приложений</b> — стр. {page + 1}/{total_pages}",
        reply_markup=_delete_keyboard(apps, page, total),
    )
    await cq.answer()


@router.callback_query(F.data == "delclose")
async def delete_close(cq: CallbackQuery):
    if not is_admin(cq.from_user.id):
        return
    await cq.message.delete()
    await cq.answer()


@router.callback_query(F.data.startswith("delinfo_"))
async def delete_info(cq: CallbackQuery):
    if not is_admin(cq.from_user.id):
        return
    app_id = cq.data.split("_", 1)[1]
    app = get_app(app_id)
    if not app:
        await cq.answer(text("not_found"), show_alert=True)
        return
    await cq.message.edit_text(
        f"📋 <b>{html.escape(app['name'])}</b>\n\n"
        f"ID: <code>{app['id']}</code>\n"
        f"📂 {cat_name(app['category'])} · v{html.escape(app['version'])} · ⬇️ {app['downloads']}\n\n"
        f"Нажмите «Копировать ID», чтобы скопировать идентификатор.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📋 Копировать ID", copy_text=CopyTextButton(text=app["id"]))],
                [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delconf_{app['id']}")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="delback")],
            ]
        ),
    )
    await cq.answer()


@router.callback_query(F.data == "delback")
async def delete_back(cq: CallbackQuery):
    if not is_admin(cq.from_user.id):
        return
    total = count_apps()
    apps = list_apps(page=0, per_page=ADMIN_PER_PAGE)
    total_pages = max(1, (total + ADMIN_PER_PAGE - 1) // ADMIN_PER_PAGE)
    await cq.message.edit_text(
        f"🗑 <b>Удаление приложений</b> — стр. 1/{total_pages}",
        reply_markup=_delete_keyboard(apps, 0, total),
    )
    await cq.answer()


@router.callback_query(F.data.startswith("delconf_"))
async def confirm_delete(cq: CallbackQuery):
    if not is_admin(cq.from_user.id):
        return
    app_id = cq.data.split("_", 1)[1]
    app = get_app(app_id)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"delyes_{app_id}"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="delback"),
            ]
        ]
    )
    if app:
        await cq.message.edit_text(
            f"⚠️ Удалить приложение <b>{html.escape(app['name'])}</b>?\n\n"
            f"ID: <code>{app['id']}</code>\n"
            f"Файл будет удалён безвозвратно.",
            reply_markup=kb,
        )
    else:
        await cq.answer(text("not_found"), show_alert=True)
        return
    await cq.answer()


@router.callback_query(F.data.startswith("delyes_"))
async def do_delete(cq: CallbackQuery):
    if not is_admin(cq.from_user.id):
        return
    app_id = cq.data.split("_", 1)[1]
    app = get_app(app_id)
    remove_app(app_id)
    if app:
        await cq.message.edit_text(
            f"✅ Удалено: <b>{html.escape(app['name'])}</b>\nID: <code>{app['id']}</code>"
        )
    else:
        await cq.message.edit_text(text("deleted"))
    await cq.answer()


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if not is_admin(message.from_user.id):
        return
    total_apps, total_downloads, total_users, top = get_stats()
    top_lines = "\n".join(
        f"{i+1}. {a['icon_emoji']} {html.escape(a['name'])} — {a['downloads']}⬇️"
        for i, a in enumerate(top)
    ) if top else "—"
    await message.answer(
        text("stats", apps=total_apps, downloads=total_downloads, users=total_users, top=top_lines)
    )


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.set_state(BroadcastState.text)
    await message.answer(text("broadcast_what"))


@router.message(BroadcastState.text)
async def broadcast_send(message: Message, state: FSMContext, bot: Bot):
    msg_text = message.text
    if not msg_text:
        return
    user_ids = all_user_ids()
    total = len(user_ids)
    sent = 0
    progress_msg = await message.answer(text("broadcast_progress", sent=0, total=total))
    for uid in user_ids:
        try:
            await bot.send_message(uid, msg_text)
            sent += 1
        except Exception:
            pass
        if sent % 10 == 0:
            try:
                await progress_msg.edit_text(text("broadcast_progress", sent=sent, total=total))
            except Exception:
                pass
        await asyncio.sleep(0.05)
    await progress_msg.edit_text(text("broadcast_done", sent=sent))
    await state.clear()