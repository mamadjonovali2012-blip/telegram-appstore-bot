import html

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db import (
    list_apps, count_apps, find_apps, get_app, get_or_create_user,
    set_user_lang, increment_downloads, toggle_favorite, get_favorites,
    is_favorite, text, CATEGORIES, cat_name, size_mb,
    get_versions, versions_count, get_version,
)

router = Router()
PER_PAGE = 8

_search_queries = {}


def _paginate_keyboard(apps, page, total, prefix="page"):
    kb = InlineKeyboardBuilder()
    for a in apps:
        kb.button(text=f"{a['icon_emoji']} {a['name']}", callback_data=f"app_{a['id']}")
    kb.adjust(2)
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"{prefix}_{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"{prefix}_{page + 1}"))
    if nav:
        kb.row(*nav)
    return kb.as_markup()


def _app_card(app, lang="ru"):
    return text("app_card", lang=lang,
        emoji=app["icon_emoji"],
        name=html.escape(app["name"]),
        version=html.escape(app["version"]),
        desc=html.escape(app["description"]),
        fname=html.escape(app["file_name"]),
        size=size_mb(app["size"]),
        downloads=app["downloads"],
        cat=cat_name(app["category"], lang),
    )


def _main_menu(lang="ru"):
    kb = InlineKeyboardBuilder()
    kb.button(text=text("new_apps", lang), callback_data="main_new")
    kb.button(text=text("top_apps", lang), callback_data="main_top")
    for key, emoji in CATEGORIES.items():
        kb.button(text=f"{emoji} {cat_name(key, lang)}", callback_data=f"cat_{key}")
    kb.button(text=text("favorites", lang), callback_data="main_fav")
    kb.button(text="🔍 Search", callback_data="main_search")
    kb.button(text="🌐 Language", callback_data="main_lang")
    kb.adjust(2, 2, 2, 2, 1, 1)
    return kb.as_markup()


def _app_kb(app, user_id, lang):
    fav = is_favorite(user_id, app["id"])
    n_versions = versions_count(app["id"])
    kb = InlineKeyboardBuilder()
    kb.button(text=text("download", lang), callback_data=f"dl_{app['id']}")
    kb.button(text=f"📦 Версии ({n_versions})", callback_data=f"vers_{app['id']}")
    kb.button(text=text("fav_btn_remove" if fav else "fav_btn_add", lang), callback_data=f"fav_{app['id']}")
    kb.button(text=text("back", lang), callback_data="main_menu")
    kb.adjust(1)
    return kb.as_markup()


@router.message(Command("start"))
async def cmd_start(message: Message):
    user = get_or_create_user(message.from_user.id)
    await message.answer(text("welcome", user["lang"]), reply_markup=_main_menu(user["lang"]))


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    user = get_or_create_user(message.from_user.id)
    await message.answer(text("choose", user["lang"]), reply_markup=_main_menu(user["lang"]))


@router.callback_query(F.data == "main_menu")
async def main_menu_cb(cq: CallbackQuery):
    user = get_or_create_user(cq.from_user.id)
    await cq.message.edit_text(text("choose", user["lang"]), reply_markup=_main_menu(user["lang"]))
    await cq.answer()


# --- Category listing ---

@router.callback_query(F.data.startswith("cat_"))
async def on_category(cq: CallbackQuery):
    cat = cq.data.split("_", 1)[1]
    if cat not in CATEGORIES:
        return
    user = get_or_create_user(cq.from_user.id)
    total = count_apps(category=cat)
    if total == 0:
        await cq.answer(text("no_apps", user["lang"]), show_alert=True)
        return
    apps = list_apps(category=cat, sort="new", page=0, per_page=PER_PAGE)
    await cq.message.edit_text(
        text("category_title", user["lang"], emoji=CATEGORIES[cat], cat_name=cat_name(cat, user["lang"])),
        reply_markup=_paginate_keyboard(apps, 0, total, prefix=f"cp_{cat}"),
    )
    await cq.answer()


@router.callback_query(F.data.startswith("cp_"))
async def on_category_page(cq: CallbackQuery):
    parts = cq.data.split("_", 2)
    cat = parts[1]
    page = int(parts[2])
    if cat not in CATEGORIES:
        return
    user = get_or_create_user(cq.from_user.id)
    total = count_apps(category=cat)
    apps = list_apps(category=cat, sort="new", page=page, per_page=PER_PAGE)
    await cq.message.edit_text(
        text("category_title", user["lang"], emoji=CATEGORIES[cat], cat_name=cat_name(cat, user["lang"])),
        reply_markup=_paginate_keyboard(apps, page, total, prefix=f"cp_{cat}"),
    )
    await cq.answer()


# --- New / Top ---

@router.callback_query(F.data == "main_new")
async def on_new(cq: CallbackQuery):
    user = get_or_create_user(cq.from_user.id)
    total = count_apps()
    if total == 0:
        await cq.answer(text("no_apps", user["lang"]), show_alert=True)
        return
    apps = list_apps(sort="new", page=0, per_page=PER_PAGE)
    await cq.message.edit_text(
        f"🆕 {text('new_apps', user['lang'])}",
        reply_markup=_paginate_keyboard(apps, 0, total, prefix="np"),
    )
    await cq.answer()


@router.callback_query(F.data.startswith("np_"))
async def on_new_page(cq: CallbackQuery):
    page = int(cq.data.split("_", 1)[1])
    user = get_or_create_user(cq.from_user.id)
    total = count_apps()
    apps = list_apps(sort="new", page=page, per_page=PER_PAGE)
    await cq.message.edit_text(
        f"🆕 {text('new_apps', user['lang'])}",
        reply_markup=_paginate_keyboard(apps, page, total, prefix="np"),
    )
    await cq.answer()


@router.callback_query(F.data == "main_top")
async def on_top(cq: CallbackQuery):
    user = get_or_create_user(cq.from_user.id)
    total = count_apps()
    if total == 0:
        await cq.answer(text("no_apps", user["lang"]), show_alert=True)
        return
    apps = list_apps(sort="top", page=0, per_page=PER_PAGE)
    await cq.message.edit_text(
        f"🏆 {text('top_apps', user['lang'])}",
        reply_markup=_paginate_keyboard(apps, 0, total, prefix="tp"),
    )
    await cq.answer()


@router.callback_query(F.data.startswith("tp_"))
async def on_top_page(cq: CallbackQuery):
    page = int(cq.data.split("_", 1)[1])
    user = get_or_create_user(cq.from_user.id)
    total = count_apps()
    apps = list_apps(sort="top", page=page, per_page=PER_PAGE)
    await cq.message.edit_text(
        f"🏆 {text('top_apps', user['lang'])}",
        reply_markup=_paginate_keyboard(apps, page, total, prefix="tp"),
    )
    await cq.answer()


# --- App card ---

@router.callback_query(F.data.startswith("app_"))
async def on_app(cq: CallbackQuery):
    app_id = cq.data.split("_", 1)[1]
    app = get_app(app_id)
    if not app:
        await cq.answer(text("not_found"), show_alert=True)
        return
    user = get_or_create_user(cq.from_user.id)
    await cq.message.edit_text(_app_card(app, user["lang"]), reply_markup=_app_kb(app, cq.from_user.id, user["lang"]))
    await cq.answer()


# --- Download ---

@router.callback_query(F.data.startswith("dl_"))
async def on_download(cq: CallbackQuery, bot: Bot):
    app_id = cq.data.split("_", 1)[1]
    app = get_app(app_id)
    if not app:
        await cq.answer(text("not_found"), show_alert=True)
        return
    increment_downloads(app_id)
    await cq.message.answer_document(
        app["file_id"],
        caption=f"{app['icon_emoji']} {html.escape(app['name'])} v{html.escape(app['version'])}",
    )
    await cq.answer(text("downloaded", name=html.escape(app["name"])))


# --- Versions ---

@router.callback_query(F.data.startswith("vers_"))
async def on_versions(cq: CallbackQuery):
    app_id = cq.data.split("_", 1)[1]
    app = get_app(app_id)
    if not app:
        await cq.answer(text("not_found"), show_alert=True)
        return
    versions = get_versions(app_id)
    if not versions:
        await cq.answer(text("no_apps"), show_alert=True)
        return
    kb = InlineKeyboardBuilder()
    for v in versions:
        label = f"v{v['version']} — {v['file_name']} ({size_mb(v['size'])} MB)"
        kb.button(text=label, callback_data=f"vdl_{v['id']}")
    kb.button(text=text("back", "ru"), callback_data=f"app_{app_id}")
    kb.adjust(1)
    await cq.message.edit_text(
        f"📦 <b>{html.escape(app['name'])}</b> — выберите версию:",
        reply_markup=kb.as_markup(),
    )
    await cq.answer()


@router.callback_query(F.data.startswith("vdl_"))
async def on_version_download(cq: CallbackQuery, bot: Bot):
    version_id = cq.data.split("_", 1)[1]
    version = get_version(version_id)
    if not version:
        await cq.answer(text("not_found"), show_alert=True)
        return
    increment_downloads(version["app_id"])
    await cq.message.answer_document(
        version["file_id"],
        caption=f"📦 {html.escape(version['file_name'])} (v{html.escape(version['version'])})",
    )
    await cq.answer(text("downloaded", name=html.escape(version["file_name"])))


# --- Favorites ---

@router.callback_query(F.data.startswith("fav_"))
async def on_favorite(cq: CallbackQuery):
    app_id = cq.data.split("_", 1)[1]
    user = get_or_create_user(cq.from_user.id)
    added = toggle_favorite(cq.from_user.id, app_id)
    app = get_app(app_id)
    if app:
        await cq.message.edit_text(_app_card(app, user["lang"]), reply_markup=_app_kb(app, cq.from_user.id, user["lang"]))
    await cq.answer(text("fav_added" if added else "fav_removed", user["lang"]))


@router.callback_query(F.data == "main_fav")
async def on_favorites_list(cq: CallbackQuery):
    user = get_or_create_user(cq.from_user.id)
    favs = get_favorites(cq.from_user.id)
    if not favs:
        await cq.answer(text("no_favorites", user["lang"]), show_alert=True)
        return
    kb = InlineKeyboardBuilder()
    for a in favs:
        kb.button(text=f"{a['icon_emoji']} {a['name']}", callback_data=f"app_{a['id']}")
    kb.adjust(2)
    kb.button(text=text("back", user["lang"]), callback_data="main_menu")
    await cq.message.edit_text(f"⭐ {text('favorites', user['lang'])}", reply_markup=kb.as_markup())
    await cq.answer()


# --- Search ---

@router.callback_query(F.data == "main_search")
async def on_search_btn(cq: CallbackQuery):
    user = get_or_create_user(cq.from_user.id)
    await cq.message.edit_text(text("search_hint", user["lang"]))
    await cq.answer()


@router.message(Command("search"))
async def cmd_search(message: Message):
    user = get_or_create_user(message.from_user.id)
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(text("search_hint", user["lang"]))
        return
    query = parts[1].strip()
    _search_queries[message.from_user.id] = query
    total, results = find_apps(query, page=0, per_page=PER_PAGE)
    if total == 0:
        await message.answer(text("no_results", user["lang"], q=html.escape(query)))
        return
    await message.answer(
        text("search_results", user["lang"], q=html.escape(query)),
        reply_markup=_paginate_keyboard(results, 0, total, prefix="sq"),
    )


@router.callback_query(F.data.startswith("sq_"))
async def on_search_page(cq: CallbackQuery):
    page = int(cq.data.split("_", 1)[1])
    user = get_or_create_user(cq.from_user.id)
    query = _search_queries.get(cq.from_user.id)
    if not query:
        await cq.answer(text("search_hint", user["lang"]))
        return
    total, results = find_apps(query, page=page, per_page=PER_PAGE)
    await cq.message.edit_text(
        text("search_results", user["lang"], q=html.escape(query)),
        reply_markup=_paginate_keyboard(results, page, total, prefix="sq"),
    )
    await cq.answer()


# --- Language ---

@router.callback_query(F.data == "main_lang")
async def on_language(cq: CallbackQuery):
    user = get_or_create_user(cq.from_user.id)
    kb = InlineKeyboardBuilder()
    kb.button(text="🇷🇺 Русский", callback_data="lang_ru")
    kb.button(text="🇬🇧 English", callback_data="lang_en")
    kb.button(text=text("back", user["lang"]), callback_data="main_menu")
    await cq.message.edit_text(text("select_lang", user["lang"]), reply_markup=kb.as_markup())
    await cq.answer()


@router.callback_query(F.data.startswith("lang_"))
async def on_language_set(cq: CallbackQuery):
    code = cq.data.split("_", 1)[1]
    set_user_lang(cq.from_user.id, code)
    await cq.message.edit_text(text("lang_changed", code), reply_markup=_main_menu(code))
    await cq.answer()