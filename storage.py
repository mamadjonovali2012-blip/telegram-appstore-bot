import json
import os
import uuid

DB_FILE = os.getenv("DB_FILE", "apps.json")


class App:
    def __init__(self, app_id, name, description, file_id, file_name, size, added_by):
        self.id = app_id
        self.name = name
        self.description = description
        self.file_id = file_id
        self.file_name = file_name
        self.size = size
        self.added_by = added_by

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "file_id": self.file_id,
            "file_name": self.file_name,
            "size": self.size,
            "added_by": self.added_by,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            data["id"],
            data["name"],
            data["description"],
            data["file_id"],
            data["file_name"],
            data["size"],
            data["added_by"],
        )


def _load():
    if not os.path.exists(DB_FILE):
        return []
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return [App.from_dict(d) for d in json.load(f)]


def _save(apps):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump([a.to_dict() for a in apps], f, ensure_ascii=False, indent=2)


def list_apps():
    return sorted(_load(), key=lambda a: a.name.lower())


def get_app(app_id):
    for app in _load():
        if app.id == app_id:
            return app
    return None


def find_apps(query):
    q = query.lower()
    return [a for a in list_apps() if q in a.name.lower() or q in a.description.lower()]


def add_app(name, description, file_id, file_name, size, added_by):
    apps = _load()
    app = App(uuid.uuid4().hex[:12], name, description, file_id, file_name, size, added_by)
    apps.append(app)
    _save(apps)
    return app


def remove_app(app_id):
    apps = _load()
    apps = [a for a in apps if a.id != app_id]
    _save(apps)