import html
import asyncio
import logging

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_IDS
from db import (
    add_app, remove_app, get_app, update_app, get_stats,
    all_user_ids, text, CATEGORIES, cat_name, size_mb,
)

router = Router()


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
    from db import list_apps
    apps = list_apps()
    if not apps:
        await message.answer(text("no_apps"))
        return
    kb = InlineKeyboardBuilder()
    for a in apps:
        kb.button(text=f"{a['icon_emoji']} {a['name']}", callback_data=f"del_{a['id']}")
    kb.adjust(1)
    await message.answer(text("rm_hint"), reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("del_"))
async def confirm_delete(cq: CallbackQuery):
    app_id = cq.data.split("_", 1)[1]
    remove_app(app_id)
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