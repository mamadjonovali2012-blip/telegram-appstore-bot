from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import ADMIN_IDS
from storage import add_app, remove_app, list_apps

router = Router()


class UploadState(StatesGroup):
    waiting_for_name = State()
    waiting_for_description = State()
    waiting_for_file = State()


def is_admin(user_id):
    return user_id in ADMIN_IDS


@router.message(Command("upload"))
async def cmd_upload(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет прав на загрузку.")
        return
    await state.set_state(UploadState.waiting_for_name)
    await message.answer("Введите название приложения:")


@router.message(UploadState.waiting_for_name)
async def upload_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(UploadState.waiting_for_description)
    await message.answer("Введите описание приложения:")


@router.message(UploadState.waiting_for_description)
async def upload_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    await state.set_state(UploadState.waiting_for_file)
    await message.answer("Отправьте файл приложения:")


@router.message(UploadState.waiting_for_file, F.document)
async def upload_file(message: Message, state: FSMContext):
    data = await state.get_data()
    doc = message.document
    app = add_app(
        name=data["name"],
        description=data["description"],
        file_id=doc.file_id,
        file_name=doc.file_name,
        size=doc.file_size,
        added_by=message.from_user.id,
    )
    await state.clear()
    await message.answer(f"✅ Приложение «{app.name}» добавлено (ID: `{app.id}`).")


@router.message(UploadState.waiting_for_file)
async def upload_file_invalid(message: Message):
    await message.answer("Пожалуйста, отправьте файл документом.")


@router.message(Command("delete"))
async def cmd_delete(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Нет прав.")
        return
    apps = list_apps()
    if not apps:
        await message.answer("Приложений нет.")
        return
    await message.answer(
        "Выберите ID приложения для удаления:\n"
        + "\n".join(f"`{a.id}` — {a.name}" for a in apps)
    )


@router.message(Command("rm"))
async def cmd_rm(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Нет прав.")
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Укажите ID: /rm <id>")
        return
    app_id = parts[1].strip()
    remove_app(app_id)
    await message.answer(f"✅ Приложение {app_id} удалено.")