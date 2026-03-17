import hashlib
import hmac
import os
import re
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from kivy.app import App
from kivy.utils import platform

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
GUEST_NAME_PATTERN = re.compile(r"^гость\s*\d+$", re.IGNORECASE)
DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "alias_online.db"


@dataclass
class Profile:
    id: int
    name: str
    email: str
    avatar_path: str | None
    bio: str | None
    created_at: str
    updated_at: str

    @property
    def initials(self):
        parts = [chunk for chunk in self.name.split() if chunk]
        if not parts:
            return "AO"

        letters = "".join(part[0] for part in parts[:2]).upper()
        return letters or "AO"

    @property
    def avatar_source(self):
        if not self.avatar_path:
            return None

        raw_path = self.avatar_path.strip()
        if raw_path.startswith(("http://", "https://", "file://")):
            return raw_path

        candidate = Path(raw_path).expanduser()
        if candidate.exists():
            return candidate.resolve().as_posix()

        return None


def _resolve_db_path(db_path=None):
    if db_path:
        path = Path(db_path)
    elif platform in ("android", "ios"):
        app = App.get_running_app()
        if app is not None and getattr(app, "user_data_dir", None):
            path = Path(app.user_data_dir) / "alias_online.db"
        else:
            path = DEFAULT_DB_PATH
    else:
        path = DEFAULT_DB_PATH

    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _legacy_desktop_db_path():
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None

    return Path(appdata) / "alias" / "alias_online.db"


def _migrate_legacy_database(target_path):
    if target_path.exists():
        return

    legacy_path = _legacy_desktop_db_path()
    if legacy_path is None or not legacy_path.exists() or legacy_path == target_path:
        return

    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(legacy_path, target_path)


def _connect(db_path=None):
    connection = sqlite3.connect(_resolve_db_path(db_path))
    connection.row_factory = sqlite3.Row
    return connection


def _normalize_text(value):
    value = (value or "").strip()
    return value or None


def _hash_password(password, salt=None):
    salt = salt or os.urandom(16).hex()
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 120000)
    return salt, derived.hex()


def _verify_password(password, salt, expected_hash):
    _, derived_hash = _hash_password(password, salt=salt)
    return hmac.compare_digest(derived_hash, expected_hash)


def _row_to_profile(row):
    if row is None:
        return None

    return Profile(
        id=row["id"],
        name=row["name"],
        email=row["email"],
        avatar_path=row["avatar_path"],
        bio=row["bio"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def initialize_database(db_path=None):
    target_path = _resolve_db_path(db_path)
    _migrate_legacy_database(target_path)

    with _connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                avatar_path TEXT,
                bio TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE VIEW IF NOT EXISTS users AS
            SELECT
                id,
                name,
                email,
                avatar_path,
                bio,
                created_at,
                updated_at
            FROM profiles
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS app_session (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                active_email TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(active_email) REFERENCES profiles(email) ON DELETE SET NULL
            )
            """
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO app_session (id, active_email)
            VALUES (1, NULL)
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS friendships (
                owner_email TEXT NOT NULL,
                friend_email TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (owner_email, friend_email),
                FOREIGN KEY(owner_email) REFERENCES profiles(email) ON DELETE CASCADE,
                FOREIGN KEY(friend_email) REFERENCES profiles(email) ON DELETE CASCADE
            )
            """
        )
        try:
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_profiles_name_unique
                ON profiles(name COLLATE NOCASE)
                """
            )
        except sqlite3.IntegrityError:
            pass


def get_database_path(db_path=None):
    return _resolve_db_path(db_path)


def get_profile_by_email(email, db_path=None):
    initialize_database(db_path)

    clean_email = (email or "").strip().lower()
    if not clean_email:
        return None

    with _connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT id, name, email, avatar_path, bio, created_at, updated_at
            FROM profiles
            WHERE email = ?
            """,
            (clean_email,),
        ).fetchone()

    return _row_to_profile(row)


def get_active_profile(db_path=None):
    initialize_database(db_path)

    with _connect(db_path) as connection:
        state = connection.execute(
            """
            SELECT active_email
            FROM app_session
            WHERE id = 1
            """
        ).fetchone()

        active_email = state["active_email"] if state is not None else None
        if not active_email:
            return None

        row = connection.execute(
            """
            SELECT id, name, email, avatar_path, bio, created_at, updated_at
            FROM profiles
            WHERE email = ?
            """,
            (active_email,),
        ).fetchone()

        if row is None:
            connection.execute(
                """
                UPDATE app_session
                SET active_email = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
                """
            )
            return None

    return _row_to_profile(row)


def set_active_profile(email=None, db_path=None):
    initialize_database(db_path)

    clean_email = (email or "").strip().lower() or None

    with _connect(db_path) as connection:
        connection.execute(
            """
            UPDATE app_session
            SET active_email = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
            """,
            (clean_email,),
        )


def save_profile(name, email, password, avatar_path=None, bio=None, db_path=None):
    initialize_database(db_path)

    clean_name = (name or "").strip()
    clean_email = (email or "").strip().lower()
    clean_avatar = _normalize_text(avatar_path)
    clean_bio = _normalize_text(bio)

    if not clean_name:
        raise ValueError("Укажи имя пользователя.")

    if GUEST_NAME_PATTERN.match(clean_name):
        raise ValueError("Ник в формате 'Гость1' зарезервирован для гостевого входа.")

    if not clean_email or not EMAIL_PATTERN.match(clean_email):
        raise ValueError("Укажи корректный e-mail.")

    if len((password or "").strip()) < 6:
        raise ValueError("Пароль должен быть не короче 6 символов.")

    salt, password_hash = _hash_password(password.strip())

    with _connect(db_path) as connection:
        existing = connection.execute("SELECT id FROM profiles WHERE email = ?", (clean_email,)).fetchone()
        name_owner = connection.execute(
            "SELECT id FROM profiles WHERE name = ? COLLATE NOCASE",
            (clean_name,),
        ).fetchone()

        if name_owner is not None and (existing is None or name_owner["id"] != existing["id"]):
            raise ValueError("Этот ник уже занят. Выбери другой.")

        if existing:
            connection.execute(
                """
                UPDATE profiles
                SET name = ?,
                    password_hash = ?,
                    password_salt = ?,
                    avatar_path = ?,
                    bio = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE email = ?
                """,
                (clean_name, password_hash, salt, clean_avatar, clean_bio, clean_email),
            )
        else:
            connection.execute(
                """
                INSERT INTO profiles (
                    name,
                    email,
                    password_hash,
                    password_salt,
                    avatar_path,
                    bio
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (clean_name, clean_email, password_hash, salt, clean_avatar, clean_bio),
            )

        row = connection.execute(
            """
            SELECT id, name, email, avatar_path, bio, created_at, updated_at
            FROM profiles
            WHERE email = ?
            """,
            (clean_email,),
        ).fetchone()

    return _row_to_profile(row)


def update_profile(email, avatar_path=None, bio=None, db_path=None):
    initialize_database(db_path)

    clean_email = (email or "").strip().lower()
    clean_avatar = _normalize_text(avatar_path)
    clean_bio = _normalize_text(bio)

    if not clean_email or not EMAIL_PATTERN.match(clean_email):
        raise ValueError("Укажи корректный e-mail.")

    with _connect(db_path) as connection:
        existing = connection.execute(
            """
            SELECT id
            FROM profiles
            WHERE email = ?
            """,
            (clean_email,),
        ).fetchone()

        if existing is None:
            raise ValueError("Профиль не найден.")

        connection.execute(
            """
            UPDATE profiles
            SET avatar_path = ?,
                bio = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE email = ?
            """,
            (clean_avatar, clean_bio, clean_email),
        )

        row = connection.execute(
            """
            SELECT id, name, email, avatar_path, bio, created_at, updated_at
            FROM profiles
            WHERE email = ?
            """,
            (clean_email,),
        ).fetchone()

    return _row_to_profile(row)


def get_latest_profile(db_path=None):
    initialize_database(db_path)

    with _connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT id, name, email, avatar_path, bio, created_at, updated_at
            FROM profiles
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """
        ).fetchone()

    return _row_to_profile(row)


def list_profiles(db_path=None):
    initialize_database(db_path)

    with _connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT id, name, email, avatar_path, bio, created_at, updated_at
            FROM profiles
            ORDER BY created_at ASC, id ASC
            """
        ).fetchall()

    return [_row_to_profile(row) for row in rows]


def search_profiles(query, exclude_email=None, db_path=None, limit=12):
    initialize_database(db_path)

    clean_query = (query or "").strip()
    clean_exclude = (exclude_email or "").strip().lower() or None

    if not clean_query:
        return []

    filters = ["name LIKE ? COLLATE NOCASE"]
    params = [f"%{clean_query}%"]

    if clean_query.isdigit():
        filters.append("CAST(id AS TEXT) = ?")
        params.append(clean_query)

    sql = f"""
        SELECT id, name, email, avatar_path, bio, created_at, updated_at
        FROM profiles
        WHERE ({' OR '.join(filters)})
    """

    if clean_exclude:
        sql += " AND email != ?"
        params.append(clean_exclude)

    sql += """
        ORDER BY
            CASE
                WHEN CAST(id AS TEXT) = ? THEN 0
                WHEN name = ? COLLATE NOCASE THEN 1
                ELSE 2
            END,
            name COLLATE NOCASE ASC,
            id ASC
        LIMIT ?
    """
    params.extend([clean_query, clean_query, int(limit)])

    with _connect(db_path) as connection:
        rows = connection.execute(sql, params).fetchall()

    return [_row_to_profile(row) for row in rows]


def list_friend_profiles(owner_email, db_path=None):
    initialize_database(db_path)

    clean_owner = (owner_email or "").strip().lower()
    if not clean_owner:
        return []

    with _connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT p.id, p.name, p.email, p.avatar_path, p.bio, p.created_at, p.updated_at
            FROM friendships AS f
            JOIN profiles AS p ON p.email = f.friend_email
            WHERE f.owner_email = ?
            ORDER BY p.name COLLATE NOCASE ASC, p.id ASC
            """,
            (clean_owner,),
        ).fetchall()

    return [_row_to_profile(row) for row in rows]


def add_friend(owner_email, friend_email, db_path=None):
    initialize_database(db_path)

    clean_owner = (owner_email or "").strip().lower()
    clean_friend = (friend_email or "").strip().lower()

    if not clean_owner or not clean_friend:
        raise ValueError("Не удалось определить пользователя для добавления в друзья.")

    if clean_owner == clean_friend:
        raise ValueError("Нельзя добавить в друзья самого себя.")

    with _connect(db_path) as connection:
        owner = connection.execute("SELECT email FROM profiles WHERE email = ?", (clean_owner,)).fetchone()
        friend = connection.execute("SELECT email FROM profiles WHERE email = ?", (clean_friend,)).fetchone()

        if owner is None or friend is None:
            raise ValueError("Пользователь не найден.")

        existing = connection.execute(
            """
            SELECT 1
            FROM friendships
            WHERE owner_email = ? AND friend_email = ?
            """,
            (clean_owner, clean_friend),
        ).fetchone()

        if existing is not None:
            raise ValueError("Этот пользователь уже есть в друзьях.")

        connection.execute(
            """
            INSERT INTO friendships (owner_email, friend_email)
            VALUES (?, ?)
            """,
            (clean_owner, clean_friend),
        )
        connection.execute(
            """
            INSERT INTO friendships (owner_email, friend_email)
            VALUES (?, ?)
            """,
            (clean_friend, clean_owner),
        )

    return get_profile_by_email(clean_friend, db_path=db_path)


def login_profile(email, password, db_path=None):
    initialize_database(db_path)

    clean_email = (email or "").strip().lower()
    clean_password = (password or "").strip()

    if not clean_email or not EMAIL_PATTERN.match(clean_email):
        raise ValueError("Укажи корректный e-mail.")

    if not clean_password:
        raise ValueError("Укажи пароль.")

    with _connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT id, name, email, avatar_path, bio, created_at, updated_at,
                   password_hash, password_salt
            FROM profiles
            WHERE email = ?
            """,
            (clean_email,),
        ).fetchone()

        if row is None or not _verify_password(clean_password, row["password_salt"], row["password_hash"]):
            raise ValueError("Неверный e-mail или пароль.")

        connection.execute(
            """
            UPDATE profiles
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (row["id"],),
        )

        fresh_row = connection.execute(
            """
            SELECT id, name, email, avatar_path, bio, created_at, updated_at
            FROM profiles
            WHERE id = ?
            """,
            (row["id"],),
        ).fetchone()

    return _row_to_profile(fresh_row)


def has_profiles(db_path=None):
    initialize_database(db_path)

    with _connect(db_path) as connection:
        row = connection.execute("SELECT 1 FROM profiles LIMIT 1").fetchone()

    return row is not None
