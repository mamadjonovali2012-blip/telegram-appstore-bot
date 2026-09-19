from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

router = Router()

CANCEL_WORDS = {"отмена", "cancel", "стоп", "stop", "отменить"}


@router.message(Command("cancel"))
@router.message(F.text.lower().in_(CANCEL_WORDS), StateFilter("*"))
async def cancel_action(message: Message, state: FSMContext):
    current = await state.get_state()
    if current is None:
        await message.answer("Нечего отменять. Напишите /start для главного меню.")
        return
    await state.clear()
    await message.answer("✅ Действие отменено. Напишите /start для главного меню.")