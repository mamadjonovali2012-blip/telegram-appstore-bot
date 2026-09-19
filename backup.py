import asyncio
import base64
import json
import logging
import os
from datetime import datetime

import aiohttp

from db import get_conn

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "")
GITHUB_PATH = os.getenv("GITHUB_PATH", "backup/apps_db.json")


def export_data():
    conn = get_conn()
    data = {
        "version": 1,
        "exported_at": datetime.utcnow().isoformat(),
        "apps": [dict(r) for r in conn.execute("SELECT * FROM apps").fetchall()],
        "users": [dict(r) for r in conn.execute("SELECT * FROM users").fetchall()],
        "favorites": [dict(r) for r in conn.execute("SELECT * FROM favorites").fetchall()],
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def import_data(payload):
    conn = get_conn()
    data = json.loads(payload)
    cur = conn.cursor()
    cur.execute("DELETE FROM apps")
    cur.execute("DELETE FROM users")
    cur.execute("DELETE FROM favorites")
    for a in data.get("apps", []):
        cur.execute(
            "INSERT OR REPLACE INTO apps (id, name, description, category, icon_emoji, version, file_id, file_name, size, downloads, added_by, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                a["id"], a["name"], a.get("description", ""), a.get("category", "other"),
                a.get("icon_emoji", "📦"), a.get("version", "1.0"), a["file_id"],
                a.get("file_name", ""), a.get("size", 0), a.get("downloads", 0),
                a.get("added_by", 0), a.get("created_at", ""),
            ),
        )
    for u in data.get("users", []):
        cur.execute(
            "INSERT OR REPLACE INTO users (id, lang, joined_at) VALUES (?,?,?)",
            (u["id"], u.get("lang", "ru"), u.get("joined_at", "")),
        )
    for f in data.get("favorites", []):
        cur.execute(
            "INSERT OR REPLACE INTO favorites (user_id, app_id) VALUES (?,?)",
            (f["user_id"], f["app_id"]),
        )
    conn.commit()


async def _github_api(method, url, token, payload=None):
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    async with aiohttp.ClientSession() as session:
        async with session.request(method, url, headers=headers, json=payload) as resp:
            return resp.status, await resp.text()


async def push_backup():
    if not GITHUB_TOKEN or not GITHUB_REPO:
        logging.warning("GITHUB_TOKEN/GITHUB_REPO не заданы — бэкап отключён")
        return False
    content = export_data()
    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}"
    status, body = await _github_api("GET", url, GITHUB_TOKEN)
    sha = None
    if status == 200:
        try:
            sha = json.loads(body)["sha"]
        except Exception:
            pass
    payload = {"message": f"backup {datetime.utcnow().isoformat()}", "content": encoded}
    if sha:
        payload["sha"] = sha
    put_status, _ = await _github_api("PUT", url, GITHUB_TOKEN, payload)
    logging.info("Backup push: HTTP %s", put_status)
    return put_status in (200, 201)


async def restore_backup():
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return False
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}"
    status, body = await _github_api("GET", url, GITHUB_TOKEN)
    if status != 200:
        logging.info("Backup not found on GitHub, starting fresh")
        return False
    try:
        payload = json.loads(body)
        content = base64.b64decode(payload["content"]).decode("utf-8")
        import_data(content)
        logging.info("Backup restored from GitHub")
        return True
    except Exception as e:
        logging.error("Failed to restore backup: %s", e)
        return False


async def backup_loop(interval=300):
    while True:
        await asyncio.sleep(interval)
        try:
            await push_backup()
        except Exception as e:
            logging.error("Backup error: %s", e)