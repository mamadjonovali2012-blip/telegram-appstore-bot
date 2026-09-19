import sqlite3
import os
import uuid
from datetime import datetime

DB_FILE = os.getenv("DB_FILE", "apps.db")

_conn = None


def get_conn():
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _init_db()
    return _conn


def _init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS apps (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT 'other',
            icon_emoji TEXT NOT NULL DEFAULT '📦',
            version TEXT NOT NULL DEFAULT '1.0',
            file_id TEXT NOT NULL,
            file_name TEXT NOT NULL,
            size INTEGER NOT NULL DEFAULT 0,
            downloads INTEGER NOT NULL DEFAULT 0,
            added_by INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            lang TEXT NOT NULL DEFAULT 'ru',
            joined_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS favorites (
            user_id INTEGER NOT NULL,
            app_id TEXT NOT NULL,
            PRIMARY KEY (user_id, app_id)
        );

        CREATE INDEX IF NOT EXISTS idx_apps_category ON apps(category);
        CREATE INDEX IF NOT EXISTS idx_apps_downloads ON apps(downloads DESC);
        CREATE INDEX IF NOT EXISTS idx_apps_created ON apps(created_at DESC);
    """)
    conn.commit()


CATEGORIES = {
    "games": "🎮",
    "tools": "🛠",
    "education": "📚",
    "entertainment": "🎬",
    "music": "🎵",
    "productivity": "⚡",
    "social": "💬",
    "other": "📦",
}


# --- Apps ---

def add_app(name, description, category, icon_emoji, version, file_id, file_name, size, added_by):
    conn = get_conn()
    app_id = uuid.uuid4().hex[:12]
    now = datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO apps (id, name, description, category, icon_emoji, version, file_id, file_name, size, added_by, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (app_id, name, description, category, icon_emoji, version, file_id, file_name, size, added_by, now),
    )
    conn.commit()
    return app_id


def get_app(app_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM apps WHERE id=?", (app_id,)).fetchone()
    return dict(row) if row else None


def list_apps(category=None, sort="new", page=0, per_page=10):
    conn = get_conn()
    where = "WHERE category=?" if category else ""
    order = "created_at DESC" if sort == "new" else "downloads DESC"
    sql = f"SELECT * FROM apps {where} ORDER BY {order} LIMIT ? OFFSET ?"
    params = ([category] if category else []) + [per_page, page * per_page]
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def count_apps(category=None):
    conn = get_conn()
    where = "WHERE category=?" if category else ""
    params = [category] if category else []
    return conn.execute(f"SELECT COUNT(*) FROM apps {where}", params).fetchone()[0]


def find_apps(query, page=0, per_page=10):
    conn = get_conn()
    like = f"%{query}%"
    total = conn.execute("SELECT COUNT(*) FROM apps WHERE name LIKE ? OR description LIKE ?", (like, like)).fetchone()[0]
    rows = conn.execute(
        "SELECT * FROM apps WHERE name LIKE ? OR description LIKE ? ORDER BY downloads DESC LIMIT ? OFFSET ?",
        (like, like, per_page, page * per_page),
    ).fetchall()
    return total, [dict(r) for r in rows]


def increment_downloads(app_id):
    conn = get_conn()
    conn.execute("UPDATE apps SET downloads = downloads + 1 WHERE id=?", (app_id,))
    conn.commit()


def remove_app(app_id):
    conn = get_conn()
    conn.execute("DELETE FROM apps WHERE id=?", (app_id,))
    conn.execute("DELETE FROM favorites WHERE app_id=?", (app_id,))
    conn.commit()


def update_app(app_id, **kwargs):
    conn = get_conn()
    allowed = {"name", "description", "category", "icon_emoji", "version", "file_id", "file_name", "size"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k}=?" for k in updates)
    conn.execute(f"UPDATE apps SET {set_clause} WHERE id=?", (*updates.values(), app_id))
    conn.commit()


def get_stats():
    conn = get_conn()
    total_apps = conn.execute("SELECT COUNT(*) FROM apps").fetchone()[0]
    total_downloads = conn.execute("SELECT COALESCE(SUM(downloads),0) FROM apps").fetchone()[0]
    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    top = [dict(r) for r in conn.execute("SELECT * FROM apps ORDER BY downloads DESC LIMIT 5").fetchall()]
    return total_apps, total_downloads, total_users, top


# --- Users ---

def get_or_create_user(user_id, lang="ru"):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if row:
        return dict(row)
    now = datetime.utcnow().isoformat()
    conn.execute("INSERT OR IGNORE INTO users (id, lang, joined_at) VALUES (?,?,?)", (user_id, lang, now))
    conn.commit()
    return {"id": user_id, "lang": lang, "joined_at": now}


def set_user_lang(user_id, lang):
    conn = get_conn()
    conn.execute("UPDATE users SET lang=? WHERE id=?", (lang, user_id))
    conn.commit()


def all_user_ids():
    conn = get_conn()
    return [r[0] for r in conn.execute("SELECT id FROM users").fetchall()]


# --- Favorites ---

def toggle_favorite(user_id, app_id):
    conn = get_conn()
    existing = conn.execute("SELECT 1 FROM favorites WHERE user_id=? AND app_id=?", (user_id, app_id)).fetchone()
    if existing:
        conn.execute("DELETE FROM favorites WHERE user_id=? AND app_id=?", (user_id, app_id))
        conn.commit()
        return False
    conn.execute("INSERT INTO favorites (user_id, app_id) VALUES (?,?)", (user_id, app_id))
    conn.commit()
    return True


def get_favorites(user_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT a.* FROM apps a JOIN favorites f ON a.id=f.app_id WHERE f.user_id=? ORDER BY a.name",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def is_favorite(user_id, app_id):
    conn = get_conn()
    return bool(conn.execute("SELECT 1 FROM favorites WHERE user_id=? AND app_id=?", (user_id, app_id)).fetchone())


# --- Texts ---

TEXTS = {
    "ru": {
        "welcome": "📱 <b>AppStore Bot</b>\n\nМагазин приложений в Telegram.\n\nВыберите раздел в меню ниже:",
        "no_apps": "😕 Пока нет ни одного приложения.",
        "no_results": "😕 Ничего не найдено по запросу «{q}».",
        "search_hint": "🔍 Введите запрос для поиска:",
        "search_results": "🔍 Результаты по запросу «{q}»:",
        "category_title": "📂 <b>{emoji} {cat_name}</b>",
        "new_apps": "🆕 Новинки",
        "top_apps": "🏆 Популярное",
        "favorites": "⭐ Избранное",
        "no_favorites": "😕 У вас пока нет избранных приложений.",
        "app_card": "{emoji} <b>{name}</b> v{version}\n📄 {desc}\n📎 {fname} ({size} MB)\n⬇️ {downloads} скачиваний\n📂 {cat}",
        "downloaded": "📥 Файл «{name}» отправлен!",
        "fav_added": "⭐ Добавлено в избранное",
        "fav_removed": "☆ Убрано из избранного",
        "lang_changed": "✅ Язык изменён на русский",
        "admin_only": "🚫 У вас нет прав.",
        "upload_name": "Введите название приложения:",
        "upload_desc": "Введите описание приложения:",
        "upload_cat": "Выберите категорию:",
        "upload_icon": "Отправьте эмодзи для иконки (или /skip):",
        "upload_ver": "Введите версию (например 1.0):",
        "upload_file": "Отправьте файл приложения:",
        "upload_done": "✅ Приложение «{name}» добавлено!\nID: <code>{id}</code>",
        "upload_no_file": "Пожалуйста, отправьте файл документом.",
        "deleted": "✅ Приложение удалено.",
        "rm_hint": "Введите ID приложения для удаления:",
        "rm_usage": "Укажите ID: /rm &lt;id&gt;",
        "not_found": "Приложение не найдено.",
        "stats": "📊 <b>Статистика</b>\n\n📦 Всего приложений: {apps}\n⬇️ Всего скачиваний: {downloads}\n👥 Пользователей: {users}\n\n🏆 <b>Топ-5:</b>\n{top}",
        "broadcast_what": "📢 Введите текст для рассылки всем пользователям:",
        "broadcast_done": "✅ Рассылка завершена. Отправлено: {sent}",
        "broadcast_progress": "📢 Рассылка... {sent}/{total}",
        "back": "⬅️ Назад",
        "download": "📥 Скачать",
        "fav_btn_add": "⭐ В избранное",
        "fav_btn_remove": "☆ Убрать",
        "select_lang": "🌐 Выберите язык:",
        "choose": "Выберите:",
    },
    "en": {
        "welcome": "📱 <b>AppStore Bot</b>\n\nApp store in Telegram.\n\nChoose a section from the menu below:",
        "no_apps": "😕 No apps yet.",
        "no_results": "😕 Nothing found for «{q}».",
        "search_hint": "🔍 Enter search query:",
        "search_results": "🔍 Results for «{q}»:",
        "category_title": "📂 <b>{emoji} {cat_name}</b>",
        "new_apps": "🆕 New",
        "top_apps": "🏆 Top",
        "favorites": "⭐ Favorites",
        "no_favorites": "😕 You have no favorite apps yet.",
        "app_card": "{emoji} <b>{name}</b> v{version}\n📄 {desc}\n📎 {fname} ({size} MB)\n⬇️ {downloads} downloads\n📂 {cat}",
        "downloaded": "📥 File «{name}» sent!",
        "fav_added": "⭐ Added to favorites",
        "fav_removed": "☆ Removed from favorites",
        "lang_changed": "✅ Language changed to English",
        "admin_only": "🚫 No permission.",
        "upload_name": "Enter app name:",
        "upload_desc": "Enter app description:",
        "upload_cat": "Choose category:",
        "upload_icon": "Send an emoji for the icon (or /skip):",
        "upload_ver": "Enter version (e.g. 1.0):",
        "upload_file": "Send the app file:",
        "upload_done": "✅ App «{name}» added!\nID: <code>{id}</code>",
        "upload_no_file": "Please send a file as a document.",
        "deleted": "✅ App deleted.",
        "rm_hint": "Enter the app ID to delete:",
        "rm_usage": "Specify ID: /rm &lt;id&gt;",
        "not_found": "App not found.",
        "stats": "📊 <b>Statistics</b>\n\n📦 Total apps: {apps}\n⬇️ Total downloads: {downloads}\n👥 Users: {users}\n\n🏆 <b>Top 5:</b>\n{top}",
        "broadcast_what": "📢 Enter text to broadcast to all users:",
        "broadcast_done": "✅ Broadcast complete. Sent: {sent}",
        "broadcast_progress": "📢 Broadcasting... {sent}/{total}",
        "back": "⬅️ Back",
        "download": "📥 Download",
        "fav_btn_add": "⭐ Favorite",
        "fav_btn_remove": "☆ Unfavorite",
        "select_lang": "🌐 Select language:",
        "choose": "Choose:",
    },
}

CATEGORY_NAMES = {
    "ru": {"games": "Игры", "tools": "Инструменты", "education": "Обучение", "entertainment": "Развлечения", "music": "Музыка", "productivity": "Продуктивность", "social": "Социальные", "other": "Прочее"},
    "en": {"games": "Games", "tools": "Tools", "education": "Education", "entertainment": "Entertainment", "music": "Music", "productivity": "Productivity", "social": "Social", "other": "Other"},
}


def text(key, lang="ru", **fmt):
    t = TEXTS.get(lang, TEXTS["ru"]).get(key, key)
    return t.format(**fmt) if fmt else t


def cat_name(key, lang="ru"):
    return CATEGORY_NAMES.get(lang, CATEGORY_NAMES["ru"]).get(key, key)


def size_mb(size):
    return round(size / (1024 * 1024), 2) if size else 0