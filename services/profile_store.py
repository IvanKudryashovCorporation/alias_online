import hashlib
import hmac
import os
import re
import shutil
import sqlite3
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from kivy.app import App
from kivy.utils import platform

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
GUEST_NAME_PATTERN = re.compile(r"^гость\s*\d+$", re.IGNORECASE)
DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "alias_online.db"
ROOM_CREATION_COST = 25
STARTER_ALIAS_COINS = 100
GUESSER_COIN_REWARD = 5
EXPLAINER_COIN_REWARD = 3
PROFILE_COLUMNS = (
    "id, name, email, avatar_path, bio, alias_coins, games_played, total_points, rooms_created, "
    "guessed_words, explained_words, match_penalty_until, match_penalty_reason, "
    "created_at, updated_at"
)


@dataclass
class Profile:
    id: int
    name: str
    email: str
    avatar_path: str | None
    bio: str | None
    alias_coins: int
    games_played: int
    total_points: int
    rooms_created: int
    guessed_words: int
    explained_words: int
    match_penalty_until: str | None
    match_penalty_reason: str | None
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


def _mobile_data_root():
    app = App.get_running_app()
    user_data_dir = getattr(app, "user_data_dir", None) if app is not None else None
    if user_data_dir:
        return Path(user_data_dir)

    if platform == "android":
        with suppress(Exception):
            from android.storage import app_storage_path

            storage_path = app_storage_path()
            if storage_path:
                return Path(storage_path)

    return Path.home() / ".alias_online"


def _resolve_db_path(db_path=None):
    if db_path:
        path = Path(db_path)
    elif platform in ("android", "ios"):
        path = _mobile_data_root() / "alias_online.db"
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


def _table_columns(connection, table_name):
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


def _ensure_profile_schema(connection):
    columns = _table_columns(connection, "profiles")
    for column_name, definition in (
        ("alias_coins", f"INTEGER NOT NULL DEFAULT {STARTER_ALIAS_COINS}"),
        ("games_played", "INTEGER NOT NULL DEFAULT 0"),
        ("total_points", "INTEGER NOT NULL DEFAULT 0"),
        ("rooms_created", "INTEGER NOT NULL DEFAULT 0"),
        ("guessed_words", "INTEGER NOT NULL DEFAULT 0"),
        ("explained_words", "INTEGER NOT NULL DEFAULT 0"),
        ("match_penalty_until", "TEXT"),
        ("match_penalty_reason", "TEXT"),
    ):
        if column_name not in columns:
            connection.execute(f"ALTER TABLE profiles ADD COLUMN {column_name} {definition}")

    connection.execute(
        """
        UPDATE profiles
        SET alias_coins = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE alias_coins = 0
          AND games_played = 0
          AND total_points = 0
          AND rooms_created = 0
        """,
        (STARTER_ALIAS_COINS,),
    )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS room_progress_claims (
            profile_email TEXT NOT NULL,
            room_code TEXT NOT NULL,
            last_score_seen INTEGER NOT NULL DEFAULT 0,
            game_counted INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (profile_email, room_code),
            FOREIGN KEY(profile_email) REFERENCES profiles(email) ON DELETE CASCADE
        )
        """
    )
    connection.execute("DROP VIEW IF EXISTS users")
    connection.execute(
        f"""
        CREATE VIEW users AS
        SELECT {PROFILE_COLUMNS}
        FROM profiles
        """
    )


def _normalize_text(value):
    value = (value or "").strip()
    return value or None


def _utc_now():
    return datetime.utcnow()


def _parse_timestamp(raw_value):
    raw = (raw_value or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _hash_password(password, salt=None):
    salt = salt or os.urandom(16).hex()
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 120000)
    return salt, derived.hex()


def _verify_password(password, salt, expected_hash):
    _, derived_hash = _hash_password(password, salt=salt)
    return hmac.compare_digest(derived_hash, expected_hash)


def _fetch_profile_row(connection, where_clause, params=()):
    return connection.execute(
        f"""
        SELECT {PROFILE_COLUMNS}
        FROM profiles
        WHERE {where_clause}
        """,
        params,
    ).fetchone()


def _row_to_profile(row):
    if row is None:
        return None

    keys = set(row.keys())
    return Profile(
        id=row["id"],
        name=row["name"],
        email=row["email"],
        avatar_path=row["avatar_path"],
        bio=row["bio"],
        alias_coins=int(row["alias_coins"]) if "alias_coins" in keys and row["alias_coins"] is not None else 0,
        games_played=int(row["games_played"]) if "games_played" in keys and row["games_played"] is not None else 0,
        total_points=int(row["total_points"]) if "total_points" in keys and row["total_points"] is not None else 0,
        rooms_created=int(row["rooms_created"]) if "rooms_created" in keys and row["rooms_created"] is not None else 0,
        guessed_words=int(row["guessed_words"]) if "guessed_words" in keys and row["guessed_words"] is not None else 0,
        explained_words=int(row["explained_words"]) if "explained_words" in keys and row["explained_words"] is not None else 0,
        match_penalty_until=row["match_penalty_until"] if "match_penalty_until" in keys else None,
        match_penalty_reason=row["match_penalty_reason"] if "match_penalty_reason" in keys else None,
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
        _ensure_profile_schema(connection)
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
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS blocked_profiles (
                owner_email TEXT NOT NULL,
                blocked_email TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (owner_email, blocked_email),
                FOREIGN KEY(owner_email) REFERENCES profiles(email) ON DELETE CASCADE,
                FOREIGN KEY(blocked_email) REFERENCES profiles(email) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS profile_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reporter_email TEXT NOT NULL,
                reported_email TEXT NOT NULL,
                reason TEXT NOT NULL,
                details TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(reporter_email) REFERENCES profiles(email) ON DELETE CASCADE,
                FOREIGN KEY(reported_email) REFERENCES profiles(email) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS friend_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_email TEXT NOT NULL,
                recipient_email TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(sender_email) REFERENCES profiles(email) ON DELETE CASCADE,
                FOREIGN KEY(recipient_email) REFERENCES profiles(email) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_friendships_owner
            ON friendships(owner_email, friend_email)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_blocked_profiles_owner
            ON blocked_profiles(owner_email, blocked_email)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_profile_reports_target
            ON profile_reports(reported_email, created_at DESC)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_friend_messages_pair
            ON friend_messages(sender_email, recipient_email, created_at DESC)
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
        row = _fetch_profile_row(connection, "email = ?", (clean_email,))

    return _row_to_profile(row)


def get_profile_by_name(name, db_path=None):
    initialize_database(db_path)

    clean_name = (name or "").strip()
    if not clean_name:
        return None

    with _connect(db_path) as connection:
        row = _fetch_profile_row(connection, "name = ? COLLATE NOCASE", (clean_name,))

    return _row_to_profile(row)


def are_friends(owner_email, friend_email, db_path=None):
    initialize_database(db_path)

    clean_owner = (owner_email or "").strip().lower()
    clean_friend = (friend_email or "").strip().lower()
    if not clean_owner or not clean_friend or clean_owner == clean_friend:
        return False

    with _connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT 1
            FROM friendships
            WHERE owner_email = ? AND friend_email = ?
            """,
            (clean_owner, clean_friend),
        ).fetchone()
    return row is not None


def is_blocked(owner_email, blocked_email, db_path=None):
    initialize_database(db_path)

    clean_owner = (owner_email or "").strip().lower()
    clean_blocked = (blocked_email or "").strip().lower()
    if not clean_owner or not clean_blocked or clean_owner == clean_blocked:
        return False

    with _connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT 1
            FROM blocked_profiles
            WHERE owner_email = ? AND blocked_email = ?
            """,
            (clean_owner, clean_blocked),
        ).fetchone()
    return row is not None


def get_relationship_state(viewer_email, target_email, db_path=None):
    initialize_database(db_path)

    viewer = (viewer_email or "").strip().lower()
    target = (target_email or "").strip().lower()
    if not viewer or not target:
        return {
            "viewer_email": viewer or None,
            "target_email": target or None,
            "is_self": False,
            "is_friend": False,
            "blocked_by_viewer": False,
            "blocked_viewer": False,
            "can_message": False,
            "can_add_friend": False,
        }

    is_self = viewer == target
    if is_self:
        return {
            "viewer_email": viewer,
            "target_email": target,
            "is_self": True,
            "is_friend": False,
            "blocked_by_viewer": False,
            "blocked_viewer": False,
            "can_message": False,
            "can_add_friend": False,
        }

    with _connect(db_path) as connection:
        friendship = connection.execute(
            """
            SELECT 1
            FROM friendships
            WHERE owner_email = ? AND friend_email = ?
            """,
            (viewer, target),
        ).fetchone()
        blocked_by_viewer = connection.execute(
            """
            SELECT 1
            FROM blocked_profiles
            WHERE owner_email = ? AND blocked_email = ?
            """,
            (viewer, target),
        ).fetchone()
        blocked_viewer = connection.execute(
            """
            SELECT 1
            FROM blocked_profiles
            WHERE owner_email = ? AND blocked_email = ?
            """,
            (target, viewer),
        ).fetchone()

    is_friend = friendship is not None
    blocked_from_any_side = blocked_by_viewer is not None or blocked_viewer is not None
    return {
        "viewer_email": viewer,
        "target_email": target,
        "is_self": False,
        "is_friend": is_friend,
        "blocked_by_viewer": blocked_by_viewer is not None,
        "blocked_viewer": blocked_viewer is not None,
        "can_message": bool(is_friend and not blocked_from_any_side),
        "can_add_friend": bool(not is_friend and not blocked_from_any_side),
    }


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

        row = _fetch_profile_row(connection, "email = ?", (active_email,))

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


def validate_registration_payload(name, email, password, db_path=None, allow_existing_email=False):
    initialize_database(db_path)

    clean_name = (name or "").strip()
    clean_email = (email or "").strip().lower()
    clean_password = (password or "").strip()

    if not clean_name:
        raise ValueError("Укажи имя пользователя.")

    if GUEST_NAME_PATTERN.match(clean_name):
        raise ValueError("Ник в формате 'Гость1' зарезервирован для гостевого входа.")

    if not clean_email or not EMAIL_PATTERN.match(clean_email):
        raise ValueError("Укажи корректный e-mail.")

    if len(clean_password) < 6:
        raise ValueError("Пароль должен быть не короче 6 символов.")

    with _connect(db_path) as connection:
        existing = connection.execute("SELECT id FROM profiles WHERE email = ?", (clean_email,)).fetchone()
        name_owner = connection.execute(
            "SELECT id FROM profiles WHERE name = ? COLLATE NOCASE",
            (clean_name,),
        ).fetchone()

        if existing is not None and not allow_existing_email:
            raise ValueError("Аккаунт с таким e-mail уже существует. Войди через экран входа.")

        if name_owner is not None and (existing is None or name_owner["id"] != existing["id"]):
            raise ValueError("Этот ник уже занят. Выбери другой.")

    return {
        "name": clean_name,
        "email": clean_email,
        "password": clean_password,
    }


def save_profile(name, email, password, avatar_path=None, bio=None, db_path=None):
    payload = validate_registration_payload(
        name=name,
        email=email,
        password=password,
        db_path=db_path,
        allow_existing_email=True,
    )
    clean_name = payload["name"]
    clean_email = payload["email"]
    clean_password = payload["password"]
    clean_avatar = _normalize_text(avatar_path)
    clean_bio = _normalize_text(bio)
    salt, password_hash = _hash_password(clean_password)

    with _connect(db_path) as connection:
        existing = connection.execute("SELECT id FROM profiles WHERE email = ?", (clean_email,)).fetchone()
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
                    alias_coins,
                    avatar_path,
                    bio
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (clean_name, clean_email, password_hash, salt, STARTER_ALIAS_COINS, clean_avatar, clean_bio),
            )

        row = _fetch_profile_row(connection, "email = ?", (clean_email,))

    return _row_to_profile(row)


def update_profile(email, name=None, avatar_path=None, bio=None, db_path=None):
    initialize_database(db_path)

    clean_email = (email or "").strip().lower()
    clean_name = _normalize_text(name)
    clean_avatar = _normalize_text(avatar_path)
    clean_bio = _normalize_text(bio)

    if name is not None:
        if not clean_name:
            raise ValueError("Укажи имя пользователя.")
        if GUEST_NAME_PATTERN.match(clean_name):
            raise ValueError("Ник в формате 'Гость1' зарезервирован для гостевого входа.")

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

        if clean_name is not None:
            name_owner = connection.execute(
                """
                SELECT id
                FROM profiles
                WHERE name = ? COLLATE NOCASE
                  AND email <> ?
                LIMIT 1
                """,
                (clean_name, clean_email),
            ).fetchone()
            if name_owner is not None:
                raise ValueError("Этот ник уже занят. Выбери другой.")

            connection.execute(
                """
                UPDATE profiles
                SET name = ?,
                    avatar_path = ?,
                    bio = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE email = ?
                """,
                (clean_name, clean_avatar, clean_bio, clean_email),
            )
        else:
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

        row = _fetch_profile_row(connection, "email = ?", (clean_email,))

    return _row_to_profile(row)


def get_latest_profile(db_path=None):
    initialize_database(db_path)

    with _connect(db_path) as connection:
        row = connection.execute(
            f"""
            SELECT {PROFILE_COLUMNS}
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
            f"""
            SELECT {PROFILE_COLUMNS}
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
        SELECT {PROFILE_COLUMNS}
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
            SELECT
                p.id AS id,
                p.name AS name,
                p.email AS email,
                p.avatar_path AS avatar_path,
                p.bio AS bio,
                p.alias_coins AS alias_coins,
                p.games_played AS games_played,
                p.total_points AS total_points,
                p.rooms_created AS rooms_created,
                p.guessed_words AS guessed_words,
                p.explained_words AS explained_words,
                p.match_penalty_until AS match_penalty_until,
                p.match_penalty_reason AS match_penalty_reason,
                p.created_at AS created_at,
                p.updated_at AS updated_at
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


def remove_friend(owner_email, friend_email, db_path=None):
    initialize_database(db_path)

    clean_owner = (owner_email or "").strip().lower()
    clean_friend = (friend_email or "").strip().lower()
    if not clean_owner or not clean_friend or clean_owner == clean_friend:
        return False

    with _connect(db_path) as connection:
        deleted = connection.execute(
            """
            DELETE FROM friendships
            WHERE (owner_email = ? AND friend_email = ?)
               OR (owner_email = ? AND friend_email = ?)
            """,
            (clean_owner, clean_friend, clean_friend, clean_owner),
        ).rowcount
    return bool(deleted)


def block_profile(owner_email, blocked_email, db_path=None):
    initialize_database(db_path)

    clean_owner = (owner_email or "").strip().lower()
    clean_blocked = (blocked_email or "").strip().lower()
    if not clean_owner or not clean_blocked:
        raise ValueError("Не удалось определить пользователя.")
    if clean_owner == clean_blocked:
        raise ValueError("Нельзя заблокировать самого себя.")

    with _connect(db_path) as connection:
        owner = connection.execute("SELECT email FROM profiles WHERE email = ?", (clean_owner,)).fetchone()
        blocked = connection.execute("SELECT email FROM profiles WHERE email = ?", (clean_blocked,)).fetchone()
        if owner is None or blocked is None:
            raise ValueError("Пользователь не найден.")

        connection.execute(
            """
            INSERT OR IGNORE INTO blocked_profiles (owner_email, blocked_email)
            VALUES (?, ?)
            """,
            (clean_owner, clean_blocked),
        )
        connection.execute(
            """
            DELETE FROM friendships
            WHERE (owner_email = ? AND friend_email = ?)
               OR (owner_email = ? AND friend_email = ?)
            """,
            (clean_owner, clean_blocked, clean_blocked, clean_owner),
        )
    return get_relationship_state(clean_owner, clean_blocked, db_path=db_path)


def unblock_profile(owner_email, blocked_email, db_path=None):
    initialize_database(db_path)

    clean_owner = (owner_email or "").strip().lower()
    clean_blocked = (blocked_email or "").strip().lower()
    if not clean_owner or not clean_blocked or clean_owner == clean_blocked:
        return False

    with _connect(db_path) as connection:
        deleted = connection.execute(
            """
            DELETE FROM blocked_profiles
            WHERE owner_email = ? AND blocked_email = ?
            """,
            (clean_owner, clean_blocked),
        ).rowcount
    return bool(deleted)


def report_profile(reporter_email, reported_email, reason, details=None, db_path=None):
    initialize_database(db_path)

    clean_reporter = (reporter_email or "").strip().lower()
    clean_reported = (reported_email or "").strip().lower()
    clean_reason = (reason or "").strip()
    clean_details = (details or "").strip() or None

    if not clean_reporter or not clean_reported:
        raise ValueError("Не удалось определить пользователей для жалобы.")
    if clean_reporter == clean_reported:
        raise ValueError("Нельзя пожаловаться на самого себя.")
    if not clean_reason:
        raise ValueError("Укажи причину жалобы.")
    if len(clean_reason) > 120:
        clean_reason = clean_reason[:120]
    if clean_details and len(clean_details) > 800:
        clean_details = clean_details[:800]

    with _connect(db_path) as connection:
        reporter = connection.execute("SELECT email FROM profiles WHERE email = ?", (clean_reporter,)).fetchone()
        reported = connection.execute("SELECT email FROM profiles WHERE email = ?", (clean_reported,)).fetchone()
        if reporter is None or reported is None:
            raise ValueError("Пользователь не найден.")

        connection.execute(
            """
            INSERT INTO profile_reports (reporter_email, reported_email, reason, details)
            VALUES (?, ?, ?, ?)
            """,
            (clean_reporter, clean_reported, clean_reason, clean_details),
        )
        report_id_row = connection.execute(
            """
            SELECT id, created_at
            FROM profile_reports
            WHERE id = last_insert_rowid()
            """
        ).fetchone()
    return {
        "id": int(report_id_row["id"]) if report_id_row is not None else None,
        "created_at": report_id_row["created_at"] if report_id_row is not None else None,
    }


def send_friend_message(sender_email, recipient_email, message, db_path=None):
    initialize_database(db_path)

    sender = (sender_email or "").strip().lower()
    recipient = (recipient_email or "").strip().lower()
    text = (message or "").strip()

    if not sender or not recipient:
        raise ValueError("Не удалось определить участников переписки.")
    if sender == recipient:
        raise ValueError("Нельзя отправить сообщение самому себе.")
    if not text:
        raise ValueError("Сообщение не может быть пустым.")
    if len(text) > 500:
        raise ValueError("Сообщение слишком длинное.")

    relation = get_relationship_state(sender, recipient, db_path=db_path)
    if not relation["is_friend"]:
        raise ValueError("Писать можно только друзьям.")
    if relation["blocked_by_viewer"] or relation["blocked_viewer"]:
        raise ValueError("Переписка недоступна из-за блокировки.")

    with _connect(db_path) as connection:
        sender_row = connection.execute("SELECT email FROM profiles WHERE email = ?", (sender,)).fetchone()
        recipient_row = connection.execute("SELECT email FROM profiles WHERE email = ?", (recipient,)).fetchone()
        if sender_row is None or recipient_row is None:
            raise ValueError("Пользователь не найден.")

        connection.execute(
            """
            INSERT INTO friend_messages (sender_email, recipient_email, message)
            VALUES (?, ?, ?)
            """,
            (sender, recipient, text),
        )
        row = connection.execute(
            """
            SELECT id, sender_email, recipient_email, message, created_at
            FROM friend_messages
            WHERE id = last_insert_rowid()
            """
        ).fetchone()
    return {
        "id": int(row["id"]),
        "sender_email": row["sender_email"],
        "recipient_email": row["recipient_email"],
        "message": row["message"],
        "created_at": row["created_at"],
    }


def list_friend_messages(owner_email, friend_email, db_path=None, limit=60):
    initialize_database(db_path)

    owner = (owner_email or "").strip().lower()
    friend = (friend_email or "").strip().lower()
    if not owner or not friend or owner == friend:
        return []

    relation = get_relationship_state(owner, friend, db_path=db_path)
    if not relation["is_friend"] or relation["blocked_by_viewer"] or relation["blocked_viewer"]:
        return []

    safe_limit = max(1, min(int(limit or 60), 200))
    with _connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT id, sender_email, recipient_email, message, created_at
            FROM (
                SELECT id, sender_email, recipient_email, message, created_at
                FROM friend_messages
                WHERE (sender_email = ? AND recipient_email = ?)
                   OR (sender_email = ? AND recipient_email = ?)
                ORDER BY id DESC
                LIMIT ?
            )
            ORDER BY id ASC
            """,
            (owner, friend, friend, owner, safe_limit),
        ).fetchall()

    result = []
    for row in rows:
        result.append(
            {
                "id": int(row["id"]),
                "sender_email": row["sender_email"],
                "recipient_email": row["recipient_email"],
                "message": row["message"],
                "created_at": row["created_at"],
                "is_outgoing": row["sender_email"] == owner,
            }
        )
    return result


def change_profile_password(email, current_password, new_password, db_path=None):
    initialize_database(db_path)

    clean_email = (email or "").strip().lower()
    clean_current_password = (current_password or "").strip()
    clean_new_password = (new_password or "").strip()

    if not clean_email or not EMAIL_PATTERN.match(clean_email):
        raise ValueError("Укажи корректный e-mail.")
    if not clean_current_password:
        raise ValueError("Введи текущий пароль.")
    if len(clean_new_password) < 6:
        raise ValueError("Новый пароль должен быть не короче 6 символов.")
    if clean_current_password == clean_new_password:
        raise ValueError("Новый пароль должен отличаться от текущего.")

    with _connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT id, password_hash, password_salt
            FROM profiles
            WHERE email = ?
            """,
            (clean_email,),
        ).fetchone()

        if row is None:
            raise ValueError("Профиль не найден.")
        if not _verify_password(clean_current_password, row["password_salt"], row["password_hash"]):
            raise ValueError("Текущий пароль введен неверно.")

        salt, password_hash = _hash_password(clean_new_password)
        connection.execute(
            """
            UPDATE profiles
            SET password_hash = ?,
                password_salt = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE email = ?
            """,
            (password_hash, salt, clean_email),
        )
        fresh_row = _fetch_profile_row(connection, "email = ?", (clean_email,))

    return _row_to_profile(fresh_row)


def reset_profile_password(email, new_password, db_path=None):
    initialize_database(db_path)

    clean_email = (email or "").strip().lower()
    clean_new_password = (new_password or "").strip()

    if not clean_email or not EMAIL_PATTERN.match(clean_email):
        raise ValueError("Укажи корректный e-mail.")
    if len(clean_new_password) < 6:
        raise ValueError("Новый пароль должен быть не короче 6 символов.")

    with _connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT id
            FROM profiles
            WHERE email = ?
            """,
            (clean_email,),
        ).fetchone()
        if row is None:
            raise ValueError("Аккаунт с таким e-mail не найден.")

        salt, password_hash = _hash_password(clean_new_password)
        connection.execute(
            """
            UPDATE profiles
            SET password_hash = ?,
                password_salt = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE email = ?
            """,
            (password_hash, salt, clean_email),
        )
        fresh_row = _fetch_profile_row(connection, "email = ?", (clean_email,))

    return _row_to_profile(fresh_row)


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
            f"""
            SELECT {PROFILE_COLUMNS},
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
            f"""
            SELECT {PROFILE_COLUMNS}
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


def spend_alias_coins(email, amount, db_path=None, *, increment_rooms_created=True, reason_label="действие"):
    initialize_database(db_path)

    clean_email = (email or "").strip().lower()
    spend_amount = int(amount or 0)
    if not clean_email or not EMAIL_PATTERN.match(clean_email):
        raise ValueError("Укажи корректный e-mail.")
    if spend_amount <= 0:
        raise ValueError("Сумма списания должна быть больше нуля.")

    with _connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT alias_coins
            FROM profiles
            WHERE email = ?
            """,
            (clean_email,),
        ).fetchone()

        if row is None:
            raise ValueError("Профиль не найден.")

        current_coins = int(row["alias_coins"] or 0)
        if current_coins < spend_amount:
            clean_reason = (reason_label or "действие").strip()
            raise ValueError(f"Нужно минимум {spend_amount} Alias Coin, чтобы выполнить: {clean_reason}.")

        if increment_rooms_created:
            connection.execute(
                """
                UPDATE profiles
                SET alias_coins = alias_coins - ?,
                    rooms_created = rooms_created + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE email = ?
                """,
                (spend_amount, clean_email),
            )
        else:
            connection.execute(
                """
                UPDATE profiles
                SET alias_coins = alias_coins - ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE email = ?
                """,
                (spend_amount, clean_email),
            )
        updated = _fetch_profile_row(connection, "email = ?", (clean_email,))

    return _row_to_profile(updated)


def get_matchmaking_penalty(email, db_path=None):
    initialize_database(db_path)

    clean_email = (email or "").strip().lower()
    if not clean_email or not EMAIL_PATTERN.match(clean_email):
        return {"active": False, "remaining_seconds": 0, "blocked_until": None, "reason": None}

    with _connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT match_penalty_until, match_penalty_reason
            FROM profiles
            WHERE email = ?
            """,
            (clean_email,),
        ).fetchone()

    blocked_until = _parse_timestamp(row["match_penalty_until"]) if row is not None else None
    if blocked_until is None:
        return {"active": False, "remaining_seconds": 0, "blocked_until": None, "reason": None}

    remaining_seconds = max(0, int((blocked_until - _utc_now()).total_seconds()))
    return {
        "active": remaining_seconds > 0,
        "remaining_seconds": remaining_seconds,
        "blocked_until": blocked_until.strftime("%Y-%m-%d %H:%M:%S") if remaining_seconds > 0 else None,
        "reason": (row["match_penalty_reason"] or "").strip() if row is not None and remaining_seconds > 0 else None,
    }


def apply_match_exit_penalty(email, coin_penalty=50, cooldown_minutes=5, reason="Выход из игры", db_path=None):
    initialize_database(db_path)

    clean_email = (email or "").strip().lower()
    if not clean_email or not EMAIL_PATTERN.match(clean_email):
        raise ValueError("Укажи корректный e-mail.")

    penalty_amount = max(0, int(coin_penalty or 0))
    cooldown_value = max(1, int(cooldown_minutes or 0))
    target_until = _utc_now() + timedelta(minutes=cooldown_value)
    penalty_reason = (reason or "").strip() or "Выход из игры"

    with _connect(db_path) as connection:
        row = connection.execute(
            f"""
            SELECT {PROFILE_COLUMNS}
            FROM profiles
            WHERE email = ?
            """,
            (clean_email,),
        ).fetchone()

        if row is None:
            raise ValueError("Профиль не найден.")

        current_profile = _row_to_profile(row)
        current_until = _parse_timestamp(current_profile.match_penalty_until)
        final_until = max(target_until, current_until) if current_until is not None else target_until
        current_coins = max(0, int(current_profile.alias_coins or 0))
        deducted_coins = min(current_coins, penalty_amount)
        remaining_coins = max(0, current_coins - deducted_coins)

        connection.execute(
            """
            UPDATE profiles
            SET alias_coins = ?,
                match_penalty_until = ?,
                match_penalty_reason = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE email = ?
            """,
            (remaining_coins, final_until.strftime("%Y-%m-%d %H:%M:%S"), penalty_reason, clean_email),
        )
        updated = _fetch_profile_row(connection, "email = ?", (clean_email,))

    updated_profile = _row_to_profile(updated)
    penalty_info = get_matchmaking_penalty(clean_email, db_path=db_path)
    return {
        "profile": updated_profile,
        "coins_deducted": deducted_coins,
        "remaining_coins": getattr(updated_profile, "alias_coins", remaining_coins),
        "blocked_until": penalty_info["blocked_until"],
        "remaining_seconds": penalty_info["remaining_seconds"],
        "cooldown_minutes": cooldown_value,
        "reason": penalty_reason,
    }


def sync_room_progress(email, room_code, current_score, round_started=False, role=None, db_path=None):
    initialize_database(db_path)

    clean_email = (email or "").strip().lower()
    clean_room_code = (room_code or "").strip().upper()
    if not clean_email or not EMAIL_PATTERN.match(clean_email) or not clean_room_code:
        return {"coins_awarded": 0, "game_counted": False, "profile": None}

    try:
        score_value = int(current_score or 0)
    except (TypeError, ValueError):
        score_value = 0

    round_flag = 1 if round_started else 0
    role_name = (role or "").strip().lower()

    with _connect(db_path) as connection:
        profile_exists = connection.execute(
            """
            SELECT 1
            FROM profiles
            WHERE email = ?
            """,
            (clean_email,),
        ).fetchone()
        if profile_exists is None:
            return {"coins_awarded": 0, "game_counted": False, "profile": None}

        claim = connection.execute(
            """
            SELECT last_score_seen, game_counted
            FROM room_progress_claims
            WHERE profile_email = ? AND room_code = ?
            """,
            (clean_email, clean_room_code),
        ).fetchone()

        coins_awarded = 0
        game_counted = False
        if claim is None:
            connection.execute(
                """
                INSERT INTO room_progress_claims (
                    profile_email,
                    room_code,
                    last_score_seen,
                    game_counted,
                    updated_at
                ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (clean_email, clean_room_code, score_value, round_flag),
            )
            if round_flag:
                score_delta = max(0, score_value)
                if role_name == "guesser":
                    coins_awarded = score_delta * GUESSER_COIN_REWARD
                elif role_name == "explainer":
                    coins_awarded = score_delta * EXPLAINER_COIN_REWARD
                else:
                    coins_awarded = score_delta
                guessed_words_awarded = score_delta if role_name == "guesser" else 0
                explained_words_awarded = score_delta if role_name == "explainer" else 0
                connection.execute(
                    """
                    UPDATE profiles
                    SET alias_coins = alias_coins + ?,
                        total_points = total_points + ?,
                        games_played = games_played + 1,
                        guessed_words = guessed_words + ?,
                        explained_words = explained_words + ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE email = ?
                    """,
                    (coins_awarded, coins_awarded, guessed_words_awarded, explained_words_awarded, clean_email),
                )
                game_counted = True
        else:
            previous_score = int(claim["last_score_seen"] or 0)
            previous_game_counted = int(claim["game_counted"] or 0)
            score_delta = max(0, score_value - previous_score)
            if role_name == "guesser":
                coins_awarded = score_delta * GUESSER_COIN_REWARD
            elif role_name == "explainer":
                coins_awarded = score_delta * EXPLAINER_COIN_REWARD
            else:
                coins_awarded = score_delta
            game_counted = bool(round_flag and not previous_game_counted)
            guessed_words_awarded = score_delta if role_name == "guesser" else 0
            explained_words_awarded = score_delta if role_name == "explainer" else 0

            if coins_awarded or game_counted:
                connection.execute(
                    """
                    UPDATE profiles
                    SET alias_coins = alias_coins + ?,
                        total_points = total_points + ?,
                        games_played = games_played + ?,
                        guessed_words = guessed_words + ?,
                        explained_words = explained_words + ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE email = ?
                    """,
                    (
                        coins_awarded,
                        coins_awarded,
                        1 if game_counted else 0,
                        guessed_words_awarded,
                        explained_words_awarded,
                        clean_email,
                    ),
                )

            next_game_counted = max(previous_game_counted, round_flag)
            if previous_score != score_value or previous_game_counted != next_game_counted:
                connection.execute(
                    """
                    UPDATE room_progress_claims
                    SET last_score_seen = ?,
                        game_counted = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE profile_email = ? AND room_code = ?
                    """,
                    (score_value, next_game_counted, clean_email, clean_room_code),
                )

        updated = _fetch_profile_row(connection, "email = ?", (clean_email,))

    return {
        "coins_awarded": coins_awarded,
        "game_counted": game_counted,
        "profile": _row_to_profile(updated),
    }
