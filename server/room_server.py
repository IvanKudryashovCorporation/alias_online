import argparse
import base64
import difflib
import io
import json
import os
import random
import re
import secrets
import smtplib
import sqlite3
import ssl
import string
import sys
import threading
import time
import urllib.request
import wave
from contextlib import suppress
from datetime import datetime, timedelta
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

SERVER_DIR = Path(__file__).resolve().parent
DB_PATH = SERVER_DIR / "rooms.db"

WORDS = {
    "easy": [
        "кот",
        "дом",
        "мяч",
        "книга",
        "школа",
        "океан",
        "чай",
        "лес",
        "солнце",
        "машина",
    ],
    "medium": [
        "путешествие",
        "оркестр",
        "археолог",
        "галерея",
        "планета",
        "инженер",
        "праздник",
        "маршрут",
        "мастерская",
        "архитектор",
    ],
    "hard": [
        "электромагнит",
        "кристаллизация",
        "фотосинтез",
        "инфраструктура",
        "микропроцессор",
        "метаморфоза",
        "конституция",
        "экспедиция",
        "космонавтика",
        "термодинамика",
    ],
}

DEFAULT_SMTP_HOST = "smtp.gmail.com"
DEFAULT_SMTP_PORT = 587
DEFAULT_SMTP_SSL_PORT = 465
DEFAULT_SENDER_EMAIL = "aliasgameonline@gmail.com"
DEFAULT_SMTP_APP_PASSWORD = ""
DEFAULT_SMTP_TIMEOUT_SECONDS = 20
DEFAULT_CODE_TTL_SECONDS = 10 * 60
DEFAULT_RESEND_COOLDOWN_SECONDS = 30
DEFAULT_MAX_ATTEMPTS = 5
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
GUEST_NAME_PATTERN = re.compile(r"^(?:гость|guest)\s*(\d{0,4})$", re.IGNORECASE)

_AUTH_LOCK = threading.Lock()
_PENDING_REGISTRATIONS = {}
_PENDING_PASSWORD_RESETS = {}

_BOT_POOL_NAMES = (
    "Alex",
    "Mia",
    "Leo",
    "Nora",
    "Max",
    "Eva",
    "Ryan",
    "Lina",
    "Mark",
    "Sofi",
    "Ivan",
    "Sara",
)
_BOT_NAME_MARKER = "\u2063"
_BOT_LOBBY_IDLE_SECONDS = 6
_BOT_LOBBY_MAX_PER_ROOM = 4
_BOT_TRANSCRIPT_LOOKBACK_SECONDS = 16
_BOT_TRANSCRIPT_MIN_CHUNKS = 2
_BOT_TRANSCRIPT_CACHE_TTL_SECONDS = 14
_BOT_TRANSCRIPT_CACHE = {}
_BOT_TRANSCRIPT_CACHE_LOCK = threading.Lock()

_OPENAI_API_KEY_ENV = "ALIAS_OPENAI_API_KEY"
_OPENAI_BASE_URL_ENV = "ALIAS_OPENAI_BASE_URL"
_OPENAI_TRANSCRIBE_MODEL_ENV = "ALIAS_OPENAI_TRANSCRIBE_MODEL"
_OPENAI_TRANSCRIBE_TIMEOUT_SEC = 12


def _safe_int_env(name, default):
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(1, value)


def _code_ttl_seconds():
    return _safe_int_env("ALIAS_EMAIL_CODE_TTL_SECONDS", DEFAULT_CODE_TTL_SECONDS)


def _resend_cooldown_seconds():
    return _safe_int_env("ALIAS_EMAIL_RESEND_COOLDOWN_SECONDS", DEFAULT_RESEND_COOLDOWN_SECONDS)


def _max_attempts():
    return _safe_int_env("ALIAS_EMAIL_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS)


def _smtp_sender_email():
    return (os.getenv("ALIAS_SMTP_EMAIL") or DEFAULT_SENDER_EMAIL).strip().lower()


def _smtp_app_password():
    raw = (os.getenv("ALIAS_SMTP_APP_PASSWORD") or "").strip()
    if raw:
        return raw.replace(" ", "")
    return DEFAULT_SMTP_APP_PASSWORD


def _smtp_host():
    return (os.getenv("ALIAS_SMTP_HOST") or DEFAULT_SMTP_HOST).strip()


def _smtp_port():
    return _safe_int_env("ALIAS_SMTP_PORT", DEFAULT_SMTP_PORT)


def _smtp_timeout_seconds():
    return _safe_int_env("ALIAS_SMTP_TIMEOUT_SECONDS", DEFAULT_SMTP_TIMEOUT_SECONDS)


def _smtp_tls_context():
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _smtp_error_details(error):
    details = " ".join(str(error).strip().split())
    if not details:
        details = error.__class__.__name__
    if len(details) > 140:
        details = f"{details[:137]}..."
    return details


def _generate_email_code():
    return f"{secrets.randbelow(1_000_000):06d}"


def _mask_email(email):
    local, _, domain = (email or "").partition("@")
    if not local or not domain:
        return email
    if len(local) <= 2:
        masked_local = local[0] + "*"
    else:
        masked_local = local[0] + "*" * (len(local) - 2) + local[-1]
    return f"{masked_local}@{domain}"


def _normalize_code(code):
    return "".join(character for character in (code or "") if character.isdigit())


def _send_code_email(recipient_email, code, subject=None, intro_line=None):
    sender_email = _smtp_sender_email()
    app_password = _smtp_app_password()
    if not app_password:
        raise ValueError(
            "Почтовая отправка не настроена на сервере. Укажи ALIAS_SMTP_APP_PASSWORD для аккаунта aliasgameonline@gmail.com."
        )

    message = EmailMessage()
    message["From"] = sender_email
    message["To"] = recipient_email
    message["Subject"] = (subject or "").strip() or "Код подтверждения Alias Online"
    intro = (intro_line or "").strip() or f"Твой код подтверждения для Alias Online: {code}"
    message.set_content(
        "\n".join(
            [
                "Привет!",
                "",
                intro,
                "",
                f"Код действует {_code_ttl_seconds() // 60} минут.",
                "Если ты не запрашивал действие, просто проигнорируй это письмо.",
            ]
        )
    )

    context = _smtp_tls_context()
    smtp_host = _smtp_host()
    smtp_port = int(_smtp_port())
    smtp_timeout = max(5, int(_smtp_timeout_seconds()))

    attempts = []
    if smtp_port == DEFAULT_SMTP_SSL_PORT:
        attempts.append(("ssl", smtp_port))
        attempts.append(("starttls", DEFAULT_SMTP_PORT))
    else:
        attempts.append(("starttls", smtp_port))
        if smtp_port != DEFAULT_SMTP_SSL_PORT:
            attempts.append(("ssl", DEFAULT_SMTP_SSL_PORT))

    last_error = None
    for mode, port in attempts:
        try:
            if mode == "ssl":
                with smtplib.SMTP_SSL(smtp_host, int(port), timeout=smtp_timeout, context=context) as server:
                    server.login(sender_email, app_password)
                    server.send_message(message)
                    return

            with smtplib.SMTP(smtp_host, int(port), timeout=smtp_timeout) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(sender_email, app_password)
                server.send_message(message)
                return
        except smtplib.SMTPAuthenticationError as error:
            raise ValueError("Не удалось авторизоваться в почте отправителя. Проверь ALIAS_SMTP_EMAIL и ALIAS_SMTP_APP_PASSWORD.") from error
        except (smtplib.SMTPException, OSError, ssl.SSLError) as error:
            last_error = error
            continue

    details = _smtp_error_details(last_error) if last_error is not None else "неизвестная ошибка"
    raise ValueError(
        f"Не удалось отправить письмо с кодом. Проверь интернет и SMTP-настройки сервера. Детали: {details}"
    )


def _cleanup_auth_sessions_locked(now=None):
    now = time.time() if now is None else now
    expired_registration = [
        session_id
        for session_id, record in _PENDING_REGISTRATIONS.items()
        if float(record.get("expires_at", 0)) <= now
    ]
    for session_id in expired_registration:
        _PENDING_REGISTRATIONS.pop(session_id, None)

    expired_password = [
        session_id
        for session_id, record in _PENDING_PASSWORD_RESETS.items()
        if float(record.get("expires_at", 0)) <= now
    ]
    for session_id in expired_password:
        _PENDING_PASSWORD_RESETS.pop(session_id, None)


def _begin_registration_verification(name, email, password, bio=None, avatar_path=None):
    clean_name = (name or "").strip()
    clean_email = (email or "").strip().lower()
    clean_password = (password or "").strip()
    clean_bio = (bio or "").strip() or None
    clean_avatar_path = (avatar_path or "").strip() or None

    if len(clean_name) < 2:
        raise ValueError("Имя должно содержать минимум 2 символа.")
    if not EMAIL_PATTERN.match(clean_email):
        raise ValueError("Укажи корректный e-mail.")
    if len(clean_password) < 6:
        raise ValueError("Пароль должен содержать минимум 6 символов.")

    now = time.time()
    session_id = secrets.token_urlsafe(24)
    code = _generate_email_code()
    record = {
        "session_id": session_id,
        "name": clean_name,
        "email": clean_email,
        "password": clean_password,
        "bio": clean_bio,
        "avatar_path": clean_avatar_path,
        "code": code,
        "expires_at": now + _code_ttl_seconds(),
        "resend_available_at": now + _resend_cooldown_seconds(),
        "attempts_left": _max_attempts(),
    }

    _send_code_email(record["email"], record["code"])

    with _AUTH_LOCK:
        _cleanup_auth_sessions_locked(now=now)
        for existing_id, existing in list(_PENDING_REGISTRATIONS.items()):
            if existing.get("email") == record["email"]:
                _PENDING_REGISTRATIONS.pop(existing_id, None)
        _PENDING_REGISTRATIONS[record["session_id"]] = record

    return {
        "session_id": record["session_id"],
        "masked_email": _mask_email(record["email"]),
        "expires_in": int(record["expires_at"] - now),
        "resend_in": int(record["resend_available_at"] - now),
        "attempts_left": int(record["attempts_left"]),
    }


def _registration_state(session_id):
    now = time.time()
    with _AUTH_LOCK:
        _cleanup_auth_sessions_locked(now=now)
        record = _PENDING_REGISTRATIONS.get(session_id)
        if record is None:
            raise ValueError("Сессия подтверждения не найдена. Начни регистрацию заново.")

        return {
            "session_id": record["session_id"],
            "masked_email": _mask_email(record["email"]),
            "expires_in": max(0, int(record["expires_at"] - now)),
            "resend_in": max(0, int(record["resend_available_at"] - now)),
            "attempts_left": max(0, int(record["attempts_left"])),
        }


def _resend_registration_code(session_id):
    now = time.time()
    with _AUTH_LOCK:
        _cleanup_auth_sessions_locked(now=now)
        record = _PENDING_REGISTRATIONS.get(session_id)
        if record is None:
            raise ValueError("Сессия подтверждения не найдена. Начни регистрацию заново.")

        seconds_left = int(record["resend_available_at"] - now)
        if seconds_left > 0:
            raise ValueError(f"Повторная отправка будет доступна через {seconds_left} сек.")

        email = record["email"]

    new_code = _generate_email_code()
    _send_code_email(email, new_code)

    now = time.time()
    with _AUTH_LOCK:
        record = _PENDING_REGISTRATIONS.get(session_id)
        if record is None:
            raise ValueError("Сессия подтверждения не найдена. Начни регистрацию заново.")

        record["code"] = new_code
        record["expires_at"] = now + _code_ttl_seconds()
        record["resend_available_at"] = now + _resend_cooldown_seconds()
        return {
            "session_id": record["session_id"],
            "masked_email": _mask_email(record["email"]),
            "expires_in": int(record["expires_at"] - now),
            "resend_in": int(record["resend_available_at"] - now),
            "attempts_left": max(0, int(record["attempts_left"])),
        }


def _confirm_registration_code(session_id, code):
    normalized_code = _normalize_code(code)
    if len(normalized_code) != 6:
        raise ValueError("Введи 6-значный код из письма.")

    now = time.time()
    with _AUTH_LOCK:
        _cleanup_auth_sessions_locked(now=now)
        record = _PENDING_REGISTRATIONS.get(session_id)
        if record is None:
            raise ValueError("Сессия подтверждения не найдена. Начни регистрацию заново.")

        if float(record["expires_at"]) <= now:
            _PENDING_REGISTRATIONS.pop(session_id, None)
            raise ValueError("Срок действия кода истёк. Запроси новый код.")

        if normalized_code != record["code"]:
            record["attempts_left"] = max(0, int(record["attempts_left"]) - 1)
            if record["attempts_left"] <= 0:
                _PENDING_REGISTRATIONS.pop(session_id, None)
                raise ValueError("Превышено число попыток. Начни регистрацию заново.")
            raise ValueError(f"Неверный код. Осталось попыток: {record['attempts_left']}.")

        _PENDING_REGISTRATIONS.pop(session_id, None)
        return {
            "name": record["name"],
            "email": record["email"],
            "password": record["password"],
            "bio": record["bio"],
            "avatar_path": record.get("avatar_path"),
        }


def _cancel_registration_session(session_id):
    with _AUTH_LOCK:
        _PENDING_REGISTRATIONS.pop(session_id, None)


def _begin_password_reset(email):
    clean_email = (email or "").strip().lower()
    if not EMAIL_PATTERN.match(clean_email):
        raise ValueError("Укажи корректный e-mail.")

    now = time.time()
    session_id = secrets.token_urlsafe(24)
    code = _generate_email_code()
    record = {
        "session_id": session_id,
        "email": clean_email,
        "code": code,
        "expires_at": now + _code_ttl_seconds(),
        "resend_available_at": now + _resend_cooldown_seconds(),
        "attempts_left": _max_attempts(),
    }

    _send_code_email(
        record["email"],
        record["code"],
        subject="Код восстановления пароля Alias Online",
        intro_line=f"Твой код для восстановления пароля Alias Online: {record['code']}",
    )

    with _AUTH_LOCK:
        _cleanup_auth_sessions_locked(now=now)
        for existing_id, existing in list(_PENDING_PASSWORD_RESETS.items()):
            if existing.get("email") == record["email"]:
                _PENDING_PASSWORD_RESETS.pop(existing_id, None)
        _PENDING_PASSWORD_RESETS[record["session_id"]] = record

    return {
        "session_id": record["session_id"],
        "masked_email": _mask_email(record["email"]),
        "expires_in": int(record["expires_at"] - now),
        "resend_in": int(record["resend_available_at"] - now),
        "attempts_left": int(record["attempts_left"]),
    }


def _password_reset_state(session_id):
    now = time.time()
    with _AUTH_LOCK:
        _cleanup_auth_sessions_locked(now=now)
        record = _PENDING_PASSWORD_RESETS.get(session_id)
        if record is None:
            raise ValueError("Сессия восстановления не найдена. Запроси код заново.")
        return {
            "session_id": record["session_id"],
            "masked_email": _mask_email(record["email"]),
            "expires_in": max(0, int(record["expires_at"] - now)),
            "resend_in": max(0, int(record["resend_available_at"] - now)),
            "attempts_left": max(0, int(record["attempts_left"])),
        }


def _resend_password_reset_code(session_id):
    now = time.time()
    with _AUTH_LOCK:
        _cleanup_auth_sessions_locked(now=now)
        record = _PENDING_PASSWORD_RESETS.get(session_id)
        if record is None:
            raise ValueError("Сессия восстановления не найдена. Запроси код заново.")

        seconds_left = int(record["resend_available_at"] - now)
        if seconds_left > 0:
            raise ValueError(f"Повторная отправка будет доступна через {seconds_left} сек.")

        email = record["email"]

    new_code = _generate_email_code()
    _send_code_email(
        email,
        new_code,
        subject="Код восстановления пароля Alias Online",
        intro_line=f"Твой новый код для восстановления пароля Alias Online: {new_code}",
    )

    now = time.time()
    with _AUTH_LOCK:
        record = _PENDING_PASSWORD_RESETS.get(session_id)
        if record is None:
            raise ValueError("Сессия восстановления не найдена. Запроси код заново.")

        record["code"] = new_code
        record["expires_at"] = now + _code_ttl_seconds()
        record["resend_available_at"] = now + _resend_cooldown_seconds()
        return {
            "session_id": record["session_id"],
            "masked_email": _mask_email(record["email"]),
            "expires_in": int(record["expires_at"] - now),
            "resend_in": int(record["resend_available_at"] - now),
            "attempts_left": max(0, int(record["attempts_left"])),
        }


def _confirm_password_reset_code(session_id, code):
    normalized_code = _normalize_code(code)
    if len(normalized_code) != 6:
        raise ValueError("Введи 6-значный код из письма.")

    now = time.time()
    with _AUTH_LOCK:
        _cleanup_auth_sessions_locked(now=now)
        record = _PENDING_PASSWORD_RESETS.get(session_id)
        if record is None:
            raise ValueError("Сессия восстановления не найдена. Запроси код заново.")

        if float(record["expires_at"]) <= now:
            _PENDING_PASSWORD_RESETS.pop(session_id, None)
            raise ValueError("Срок действия кода истёк. Запроси новый код.")

        if normalized_code != record["code"]:
            record["attempts_left"] = max(0, int(record["attempts_left"]) - 1)
            if record["attempts_left"] <= 0:
                _PENDING_PASSWORD_RESETS.pop(session_id, None)
                raise ValueError("Превышено число попыток. Запроси код заново.")
            raise ValueError(f"Неверный код. Осталось попыток: {record['attempts_left']}.")

        _PENDING_PASSWORD_RESETS.pop(session_id, None)
        return {"email": record["email"]}


def _cancel_password_reset_session(session_id):
    with _AUTH_LOCK:
        _PENDING_PASSWORD_RESETS.pop(session_id, None)


def configure_db_path(path):
    global DB_PATH
    DB_PATH = Path(path).expanduser()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return DB_PATH


def _resolve_mobile_storage_dir():
    # Do not import Kivy in desktop/server processes: Kivy may parse CLI args
    # and break --host/--port for this server script.
    is_android = bool(os.environ.get("ANDROID_ARGUMENT"))
    is_ios = sys.platform == "ios" or bool(os.environ.get("KIVY_BUILD") == "ios")
    if not (is_android or is_ios):
        return None

    with suppress(Exception):
        os.environ.setdefault("KIVY_NO_ARGS", "1")
        from kivy.app import App
        from kivy.utils import platform

        if platform not in ("android", "ios"):
            return None

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
    return None


def resolve_db_path():
    mobile_root = _resolve_mobile_storage_dir()
    if mobile_root is not None:
        return configure_db_path(mobile_root / "room_server" / "rooms.db")
    return DB_PATH


def _connect():
    connection = sqlite3.connect(resolve_db_path())
    connection.row_factory = sqlite3.Row
    return connection


def _utc_now():
    return datetime.utcnow()


def _dt_to_str(value):
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _now():
    return _dt_to_str(_utc_now())


def _str_to_dt(value):
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _normalize_scope(scope_value, visibility_value):
    scope = (scope_value or "").strip().lower()
    if scope in {"public", "private"}:
        return scope

    visibility = (visibility_value or "").strip().lower()
    if "публ" in visibility or "public" in visibility:
        return "public"
    return "private"


def _difficulty_key(value):
    raw = (value or "").strip().lower()
    if "лег" in raw or "easy" in raw:
        return "easy"
    if "сред" in raw or "medium" in raw:
        return "medium"
    if "слож" in raw or "hard" in raw:
        return "hard"
    return "mix"


def _pick_word(difficulty):
    key = _difficulty_key(difficulty)
    if key == "easy":
        return random.choice(WORDS["easy"])
    if key == "medium":
        return random.choice(WORDS["medium"])
    if key == "hard":
        return random.choice(WORDS["hard"])
    return random.choice(WORDS["easy"] + WORDS["medium"] + WORDS["hard"])


def _normalize_guess(value):
    compact = "".join(ch for ch in (value or "").strip().lower() if ch.isalnum())
    return compact


def _required_players_to_start(max_players):
    return 1


def _init_db():
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS rooms (
                code TEXT PRIMARY KEY,
                room_name TEXT NOT NULL,
                host_name TEXT NOT NULL,
                max_players INTEGER NOT NULL,
                difficulty TEXT NOT NULL,
                visibility TEXT NOT NULL,
                visibility_scope TEXT NOT NULL DEFAULT 'private',
                round_timer_sec INTEGER NOT NULL,
                current_explainer TEXT NOT NULL DEFAULT '',
                current_word TEXT NOT NULL DEFAULT '',
                game_phase TEXT NOT NULL DEFAULT 'lobby',
                starts_count INTEGER NOT NULL DEFAULT 0,
                countdown_end_at TEXT,
                round_end_at TEXT,
                bot_next_action_at TEXT,
                voice_speaker TEXT,
                voice_until TEXT,
                explainer_mic_muted INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS room_players (
                room_code TEXT NOT NULL,
                player_name TEXT NOT NULL,
                client_id TEXT,
                joined_at TEXT NOT NULL,
                PRIMARY KEY (room_code, player_name),
                FOREIGN KEY(room_code) REFERENCES rooms(code) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS room_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_code TEXT NOT NULL,
                player_name TEXT NOT NULL,
                message TEXT NOT NULL,
                message_type TEXT NOT NULL DEFAULT 'chat',
                created_at TEXT NOT NULL,
                FOREIGN KEY(room_code) REFERENCES rooms(code) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS room_scores (
                room_code TEXT NOT NULL,
                player_name TEXT NOT NULL,
                score INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (room_code, player_name),
                FOREIGN KEY(room_code) REFERENCES rooms(code) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS room_voice_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_code TEXT NOT NULL,
                player_name TEXT NOT NULL,
                sample_rate INTEGER NOT NULL,
                pcm16_b64 TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(room_code) REFERENCES rooms(code) ON DELETE CASCADE
            )
            """
        )

        room_columns = connection.execute("PRAGMA table_info(rooms)").fetchall()
        existing_columns = {column["name"] for column in room_columns}
        required_columns = [
            ("visibility_scope", "TEXT NOT NULL DEFAULT 'private'"),
            ("current_explainer", "TEXT NOT NULL DEFAULT ''"),
            ("current_word", "TEXT NOT NULL DEFAULT ''"),
            ("game_phase", "TEXT NOT NULL DEFAULT 'lobby'"),
            ("starts_count", "INTEGER NOT NULL DEFAULT 0"),
            ("countdown_end_at", "TEXT"),
            ("round_end_at", "TEXT"),
            ("bot_next_action_at", "TEXT"),
            ("voice_speaker", "TEXT"),
            ("voice_until", "TEXT"),
            ("explainer_mic_muted", "INTEGER NOT NULL DEFAULT 1"),
        ]
        for name, definition in required_columns:
            if name not in existing_columns:
                connection.execute(f"ALTER TABLE rooms ADD COLUMN {name} {definition}")

        player_columns = connection.execute("PRAGMA table_info(room_players)").fetchall()
        existing_player_columns = {column["name"] for column in player_columns}
        if "client_id" not in existing_player_columns:
            connection.execute("ALTER TABLE room_players ADD COLUMN client_id TEXT")

        connection.execute(
            """
            UPDATE rooms
            SET explainer_mic_muted = CASE
                WHEN explainer_mic_muted IN (0, 1) THEN explainer_mic_muted
                ELSE 1
            END
            """
        )

        room_rows = connection.execute(
            """
            SELECT code, visibility, visibility_scope, host_name, difficulty, current_explainer, current_word, game_phase, explainer_mic_muted
            FROM rooms
            """
        ).fetchall()
        for row in room_rows:
            scope = _normalize_scope(row["visibility_scope"], row["visibility"])
            explainer = (row["current_explainer"] or "").strip() or row["host_name"]
            word = (row["current_word"] or "").strip() or _pick_word(row["difficulty"])
            phase = (row["game_phase"] or "").strip().lower()
            if phase not in {"lobby", "countdown", "round"}:
                phase = "lobby"
            mic_muted = 1 if int(row["explainer_mic_muted"] or 0) not in {0, 1} else int(row["explainer_mic_muted"] or 0)
            connection.execute(
                """
                UPDATE rooms
                SET visibility_scope = ?,
                    current_explainer = ?,
                    current_word = ?,
                    game_phase = ?,
                    explainer_mic_muted = ?
                WHERE code = ?
                """,
                (scope, explainer, word, phase, mic_muted, row["code"]),
            )

        players = connection.execute(
            """
            SELECT room_code, player_name
            FROM room_players
            """
        ).fetchall()
        for player in players:
            connection.execute(
                """
                INSERT OR IGNORE INTO room_scores (room_code, player_name, score, updated_at)
                VALUES (?, ?, 0, ?)
                """,
                (player["room_code"], player["player_name"], _now()),
            )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_rooms_visibility_scope
            ON rooms(visibility_scope)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_rooms_created_at
            ON rooms(created_at DESC)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_room_messages_room_code_id
            ON room_messages(room_code, id)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_room_scores_room
            ON room_scores(room_code)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_room_players_room_client
            ON room_players(room_code, client_id)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_room_voice_chunks_room_id
            ON room_voice_chunks(room_code, id)
            """
        )


def _normalize_mic_muted_flag(value, default=1):
    fallback = 1 if int(default or 0) else 0
    if value is None or value == "":
        return fallback
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return 1 if parsed else 0


def _normalize_room(row, players_count):
    return {
        "code": row["code"],
        "room_name": row["room_name"],
        "host_name": row["host_name"],
        "max_players": row["max_players"],
        "required_players_to_start": _required_players_to_start(row["max_players"]),
        "difficulty": row["difficulty"],
        "visibility": row["visibility"],
        "visibility_scope": row["visibility_scope"],
        "round_timer_sec": row["round_timer_sec"],
        "current_explainer": row["current_explainer"],
        "current_word": row["current_word"],
        "game_phase": row["game_phase"],
        "starts_count": int(row["starts_count"] or 0),
        "countdown_end_at": row["countdown_end_at"],
        "round_end_at": row["round_end_at"],
        "bot_next_action_at": row["bot_next_action_at"],
        "voice_speaker": row["voice_speaker"],
        "voice_until": row["voice_until"],
        "explainer_mic_muted": bool(_normalize_mic_muted_flag(row["explainer_mic_muted"], default=1)),
        "players_count": players_count,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _rooms_has_legacy_rounds_column(connection):
    columns = connection.execute("PRAGMA table_info(rooms)").fetchall()
    return any((column["name"] or "").strip().lower() == "rounds" for column in columns)


def _normalize_message(row):
    return {
        "id": row["id"],
        "room_code": row["room_code"],
        "player_name": row["player_name"],
        "message": row["message"],
        "message_type": row["message_type"],
        "created_at": row["created_at"],
    }


def _normalize_score(row):
    return {
        "player_name": row["player_name"],
        "score": int(row["score"]),
    }


def _generate_room_code(connection):
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(20):
        code = "".join(random.choice(alphabet) for _ in range(6))
        existing = connection.execute("SELECT 1 FROM rooms WHERE code = ?", (code,)).fetchone()
        if existing is None:
            return code
    raise RuntimeError("Failed to generate unique room code.")


def _normalize_requested_code(value):
    raw = "".join(character for character in (value or "").upper() if character.isalnum())
    return raw[:10]


def _normalize_client_id(value):
    clean = re.sub(r"[^0-9A-Za-z_\-]", "", (value or "").strip())
    return clean[:128]


def _normalize_player_name(value):
    return (value or "").strip().casefold()


def _same_player_name(left, right):
    normalized_left = _normalize_player_name(left)
    normalized_right = _normalize_player_name(right)
    return bool(normalized_left and normalized_left == normalized_right)


def _resolve_room_player_name(connection, room_code, player_name):
    clean_player_name = (player_name or "").strip()
    if not clean_player_name:
        return ""

    exact_row = connection.execute(
        """
        SELECT player_name
        FROM room_players
        WHERE room_code = ? AND player_name = ?
        LIMIT 1
        """,
        (room_code, clean_player_name),
    ).fetchone()
    if exact_row is not None:
        return (exact_row["player_name"] or "").strip()

    normalized_target = _normalize_player_name(clean_player_name)
    if not normalized_target:
        return ""

    rows = connection.execute(
        """
        SELECT player_name
        FROM room_players
        WHERE room_code = ?
        ORDER BY joined_at ASC, rowid ASC
        """,
        (room_code,),
    ).fetchall()
    for existing in rows:
        existing_name = (existing["player_name"] or "").strip()
        if _normalize_player_name(existing_name) == normalized_target:
            return existing_name
    return ""


def _resolve_room_code(connection, requested_code=None):
    preferred = _normalize_requested_code(requested_code)
    if preferred and 4 <= len(preferred) <= 10:
        existing = connection.execute("SELECT 1 FROM rooms WHERE code = ?", (preferred,)).fetchone()
        if existing is None:
            return preferred
    return _generate_room_code(connection)


def _room_with_count(connection, room_code):
    row = connection.execute("SELECT * FROM rooms WHERE code = ?", (room_code,)).fetchone()
    if row is None:
        return None

    count_row = connection.execute(
        "SELECT COUNT(*) AS players_count FROM room_players WHERE room_code = ?",
        (room_code,),
    ).fetchone()
    return _normalize_room(row, count_row["players_count"])


def _room_players(connection, room_code):
    rows = connection.execute(
        """
        SELECT player_name
        FROM room_players
        WHERE room_code = ?
        ORDER BY joined_at ASC, rowid ASC
        """,
        (room_code,),
    ).fetchall()
    return [row["player_name"] for row in rows]


def _room_scores(connection, room_code):
    rows = connection.execute(
        """
        SELECT player_name, score
        FROM room_scores
        WHERE room_code = ?
        ORDER BY score DESC, player_name ASC
        """,
        (room_code,),
    ).fetchall()
    return [_normalize_score(row) for row in rows]


def _is_room_player(connection, room_code, player_name):
    return bool(_resolve_room_player_name(connection, room_code, player_name))


def _touch_room(connection, room_code):
    connection.execute(
        """
        UPDATE rooms
        SET updated_at = ?
        WHERE code = ?
        """,
        (_now(), room_code),
    )


def _is_bot_player(player_name):
    clean_name = (player_name or "").strip()
    if not clean_name:
        return False
    if clean_name.startswith(_BOT_NAME_MARKER):
        return True
    normalized = clean_name.lower()
    return normalized.startswith("bot ") or normalized.startswith("ai ")


def _is_guest_player_name(player_name):
    clean_name = (player_name or "").strip()
    if not clean_name:
        return False
    return bool(GUEST_NAME_PATTERN.match(clean_name))


def _guest_name_prefix(player_name):
    clean_name = (player_name or "").strip()
    if "guest" in clean_name.lower():
        return "Guest"
    return "Гость"


def _next_available_guest_name(connection, room_code, requested_name):
    prefix = _guest_name_prefix(requested_name)
    existing_players = _room_players(connection, room_code)
    occupied = {_normalize_player_name(name) for name in existing_players}
    index = 1
    while _normalize_player_name(f"{prefix}{index}") in occupied:
        index += 1
    return f"{prefix}{index}"


def _visible_player_name(player_name):
    clean_name = (player_name or "").strip()
    if clean_name.startswith(_BOT_NAME_MARKER):
        return clean_name[len(_BOT_NAME_MARKER) :]
    return clean_name


def _preferred_human_player(players):
    for player in players or []:
        if not _is_bot_player(player):
            return player
    if players:
        return players[0]
    return ""


def _pick_bot_delay_seconds():
    return random.uniform(1.6, 4.2)


def _pick_lobby_bot_delay_seconds():
    return random.uniform(2.5, 4.5)


def _next_bot_action_at(mode="round"):
    if mode == "lobby":
        return _dt_to_str(_utc_now() + timedelta(seconds=_pick_lobby_bot_delay_seconds()))
    return _dt_to_str(_utc_now() + timedelta(seconds=_pick_bot_delay_seconds()))


def _openai_api_key():
    return (os.getenv(_OPENAI_API_KEY_ENV) or "").strip()


def _ai_bots_enabled():
    # Bot auto-join is disabled for live multiplayer rooms.
    return False


def _openai_base_url():
    raw = (os.getenv(_OPENAI_BASE_URL_ENV) or "https://api.openai.com/v1").strip().rstrip("/")
    return raw or "https://api.openai.com/v1"


def _openai_transcribe_model():
    return (os.getenv(_OPENAI_TRANSCRIBE_MODEL_ENV) or "gpt-4o-mini-transcribe").strip() or "gpt-4o-mini-transcribe"


def _voice_rows_for_transcript(connection, room_code, speaker_name):
    since = _dt_to_str(_utc_now() - timedelta(seconds=_BOT_TRANSCRIPT_LOOKBACK_SECONDS))
    rows = connection.execute(
        """
        SELECT id, sample_rate, pcm16_b64
        FROM room_voice_chunks
        WHERE room_code = ? AND player_name = ? AND created_at >= ?
        ORDER BY id ASC
        LIMIT 120
        """,
        (room_code, speaker_name, since),
    ).fetchall()
    return rows


def _voice_rows_to_wav(rows):
    if not rows:
        return None, None, None

    decoded = []
    rate_counter = {}
    for row in rows:
        try:
            sample_rate = int(row["sample_rate"] or 0)
        except (TypeError, ValueError):
            sample_rate = 0
        if sample_rate < 8000 or sample_rate > 48000:
            continue
        try:
            pcm16_raw = base64.b64decode((row["pcm16_b64"] or "").encode("ascii"), validate=True)
        except Exception:
            continue
        if len(pcm16_raw) < 2:
            continue
        decoded.append((int(row["id"]), sample_rate, pcm16_raw))
        rate_counter[sample_rate] = int(rate_counter.get(sample_rate, 0)) + 1

    if len(decoded) < _BOT_TRANSCRIPT_MIN_CHUNKS:
        return None, None, None

    target_rate = max(rate_counter.items(), key=lambda pair: pair[1])[0]
    chunk_ids = []
    buffer = bytearray()
    for chunk_id, sample_rate, pcm16_raw in decoded:
        if sample_rate != target_rate:
            continue
        chunk_ids.append(chunk_id)
        buffer.extend(pcm16_raw)

    if len(chunk_ids) < _BOT_TRANSCRIPT_MIN_CHUNKS or len(buffer) < 512:
        return None, None, None

    wav_stream = io.BytesIO()
    with wave.open(wav_stream, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(target_rate)
        wav_file.writeframes(bytes(buffer))

    return wav_stream.getvalue(), max(chunk_ids), target_rate


def _build_multipart_body(*, fields, file_field, filename, content_type, file_bytes):
    boundary = f"----AliasForm{secrets.token_hex(8)}"
    body = bytearray()

    for key, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"))
        body.extend(str(value).encode("utf-8"))
        body.extend(b"\r\n")

    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(
        (
            f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
    )
    body.extend(file_bytes)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))
    return boundary, bytes(body)


def _transcribe_wav_with_openai(wav_bytes):
    api_key = _openai_api_key()
    if not api_key or not wav_bytes:
        return ""

    model = _openai_transcribe_model()
    endpoint = f"{_openai_base_url()}/audio/transcriptions"
    boundary, body = _build_multipart_body(
        fields={"model": model, "temperature": "0"},
        file_field="file",
        filename="voice.wav",
        content_type="audio/wav",
        file_bytes=wav_bytes,
    )
    request = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=_OPENAI_TRANSCRIBE_TIMEOUT_SEC) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return ""

    text = (payload.get("text") or "").strip()
    if len(text) > 220:
        text = text[:220].strip()
    return text


def _cached_bot_transcript(room_code, latest_chunk_id):
    now_ts = time.time()
    with _BOT_TRANSCRIPT_CACHE_LOCK:
        cached = _BOT_TRANSCRIPT_CACHE.get(room_code)
        if (
            cached
            and int(cached.get("latest_chunk_id") or 0) == int(latest_chunk_id or 0)
            and now_ts - float(cached.get("updated_ts") or 0.0) <= _BOT_TRANSCRIPT_CACHE_TTL_SECONDS
        ):
            return (cached.get("transcript") or "").strip()
    return ""


def _store_bot_transcript(room_code, latest_chunk_id, transcript):
    with _BOT_TRANSCRIPT_CACHE_LOCK:
        _BOT_TRANSCRIPT_CACHE[room_code] = {
            "latest_chunk_id": int(latest_chunk_id or 0),
            "transcript": (transcript or "").strip(),
            "updated_ts": time.time(),
        }


def _resolve_explainer_transcript(connection, room_code, explainer_name):
    if not _openai_api_key():
        return ""

    rows = _voice_rows_for_transcript(connection, room_code, explainer_name)
    wav_bytes, latest_chunk_id, _sample_rate = _voice_rows_to_wav(rows)
    if not wav_bytes or latest_chunk_id is None:
        return ""

    cached = _cached_bot_transcript(room_code, latest_chunk_id)
    if cached:
        return cached

    transcript = _transcribe_wav_with_openai(wav_bytes)
    _store_bot_transcript(room_code, latest_chunk_id, transcript)
    return transcript


def _word_pool_for_difficulty(difficulty):
    key = _difficulty_key(difficulty)
    if key == "easy":
        return list(WORDS["easy"])
    if key == "medium":
        return list(WORDS["medium"])
    if key == "hard":
        return list(WORDS["hard"])
    return list(WORDS["easy"] + WORDS["medium"] + WORDS["hard"])


def _extract_transcript_tokens(text):
    clean = re.sub(r"[^0-9a-zA-Zа-яА-ЯёЁ]+", " ", (text or "").lower())
    return [token for token in clean.split() if len(token) >= 3]


def _best_transcript_match(transcript, words):
    normalized_transcript = _normalize_guess(transcript)
    if not normalized_transcript or not words:
        return None, 0.0

    transcript_tokens = _extract_transcript_tokens(transcript)
    best_word = None
    best_score = 0.0
    for candidate in words:
        normalized_candidate = _normalize_guess(candidate)
        if not normalized_candidate:
            continue
        score = 0.0
        if normalized_candidate in normalized_transcript:
            score = 1.0
        if transcript_tokens:
            for token in transcript_tokens:
                score = max(score, difflib.SequenceMatcher(None, normalized_candidate, _normalize_guess(token)).ratio() * 0.92)
        score = max(score, difflib.SequenceMatcher(None, normalized_candidate, normalized_transcript).ratio() * 0.62)
        if score > best_score:
            best_word = candidate
            best_score = score
    return best_word, float(best_score)


def _humanize_bot_guess(guess_text):
    clean_guess = (guess_text or "").strip()
    if not clean_guess:
        return clean_guess
    roll = random.random()
    if roll < 0.12:
        return clean_guess.lower()
    if roll < 0.20:
        return f"{clean_guess}?"
    if roll < 0.24:
        return f"мб {clean_guess.lower()}"
    return clean_guess


def _pick_bot_name(existing_players):
    existing = {(name or "").strip().lower() for name in existing_players}
    existing_visible = {_visible_player_name(name).lower() for name in existing_players}
    pool = list(_BOT_POOL_NAMES)
    random.shuffle(pool)
    for candidate in pool:
        bot_candidate = f"{_BOT_NAME_MARKER}{candidate}"
        if bot_candidate.lower() not in existing and candidate.lower() not in existing_visible:
            return bot_candidate
    base_name = random.choice(_BOT_POOL_NAMES)
    index = 2
    while True:
        candidate = f"{_BOT_NAME_MARKER}{base_name} {index}"
        if candidate.lower() not in existing and _visible_player_name(candidate).lower() not in existing_visible:
            return candidate
        index += 1


def _schedule_lobby_bot_join(connection, room_code, seconds):
    seconds = max(2, int(seconds))
    connection.execute(
        """
        UPDATE rooms
        SET bot_next_action_at = ?,
            updated_at = ?
        WHERE code = ?
        """,
        (_dt_to_str(_utc_now() + timedelta(seconds=seconds)), _now(), room_code),
    )


def _purge_bots_if_ai_disabled(connection, room_code, players):
    if _ai_bots_enabled():
        return False
    room_row = connection.execute(
        """
        SELECT bot_next_action_at
        FROM rooms
        WHERE code = ?
        """,
        (room_code,),
    ).fetchone()
    has_scheduled_bot_action = bool(room_row and room_row["bot_next_action_at"])
    bot_players = [player for player in (players or []) if _is_bot_player(player)]
    changed = False

    if bot_players:
        changed = True
        for bot_name in bot_players:
            connection.execute(
                """
                DELETE FROM room_players
                WHERE room_code = ? AND player_name = ?
                """,
                (room_code, bot_name),
            )
            connection.execute(
                """
                DELETE FROM room_scores
                WHERE room_code = ? AND player_name = ?
                """,
                (room_code, bot_name),
            )
            connection.execute(
                """
                DELETE FROM room_voice_chunks
                WHERE room_code = ? AND player_name = ?
                """,
                (room_code, bot_name),
            )
            connection.execute(
                """
                DELETE FROM room_messages
                WHERE room_code = ?
                  AND (player_name = ? OR message LIKE ? OR message LIKE ?)
                """,
                (
                    room_code,
                    bot_name,
                    f"%{_visible_player_name(bot_name)} joined the room.%",
                    f"%{_visible_player_name(bot_name)} guessed the word.%",
                ),
            )
            changed = True
    generic_cleanup_cursor = connection.execute(
        """
        DELETE FROM room_messages
        WHERE room_code = ?
          AND (
            LOWER(player_name) LIKE 'bot%'
            OR LOWER(player_name) LIKE 'ai %'
            OR player_name LIKE ?
            OR (
              message_type = 'system'
              AND LOWER(message) LIKE '%bot%'
            )
          )
        """,
        (room_code, f"{_BOT_NAME_MARKER}%"),
    )
    if int(getattr(generic_cleanup_cursor, "rowcount", 0) or 0) > 0:
        changed = True
    reset_cursor = connection.execute(
        """
        UPDATE rooms
        SET bot_next_action_at = NULL,
            updated_at = ?
        WHERE code = ?
          AND bot_next_action_at IS NOT NULL
        """,
        (_now(), room_code),
    )
    if int(getattr(reset_cursor, "rowcount", 0) or 0) > 0:
        changed = True
    if bot_players:
        _repair_room_integrity(connection, room_code)
    return bool(changed or has_scheduled_bot_action)


def _maybe_add_lobby_bot(connection, room_code, room, players):
    if _purge_bots_if_ai_disabled(connection, room_code, players):
        return False
    if not _ai_bots_enabled():
        return False

    max_players = int(room.get("max_players") or 0)
    if max_players <= 0:
        return False
    if len(players) >= max_players:
        connection.execute(
            """
            UPDATE rooms
            SET bot_next_action_at = NULL,
                updated_at = ?
            WHERE code = ?
            """,
            (_now(), room_code),
        )
        return False

    human_players = [player for player in players if not _is_bot_player(player)]
    if not human_players:
        return False

    bot_players = [player for player in players if _is_bot_player(player)]
    if len(bot_players) >= min(_BOT_LOBBY_MAX_PER_ROOM, max(0, max_players - 1)):
        return False

    updated_dt = _str_to_dt(room.get("updated_at")) or _str_to_dt(room.get("created_at")) or _utc_now()
    idle_seconds = max(0, int((_utc_now() - updated_dt).total_seconds()))
    if idle_seconds < _BOT_LOBBY_IDLE_SECONDS and not bot_players:
        _schedule_lobby_bot_join(connection, room_code, max(1, _BOT_LOBBY_IDLE_SECONDS - idle_seconds))
        return False

    bot_name = _pick_bot_name(players)
    joined_at = _now()
    connection.execute(
        """
        INSERT INTO room_players (room_code, player_name, joined_at)
        VALUES (?, ?, ?)
        """,
        (room_code, bot_name, joined_at),
    )
    _ensure_score_row(connection, room_code, bot_name)
    _insert_message(connection, room_code, "System", f"{bot_name} joined the room.", "system")

    players_after = _room_players(connection, room_code)
    should_schedule_more = len(players_after) < max_players and (
        len([name for name in players_after if _is_bot_player(name)]) < min(_BOT_LOBBY_MAX_PER_ROOM, max(0, max_players - 1))
    )
    connection.execute(
        """
        UPDATE rooms
        SET bot_next_action_at = ?,
            updated_at = ?
        WHERE code = ?
        """,
        (_next_bot_action_at("lobby") if should_schedule_more else None, _now(), room_code),
    )
    return True


def _pick_bot_round_guess(connection, room_code, room):
    current_word = (room.get("current_word") or "").strip()
    difficulty = room.get("difficulty")
    explainer_name = (room.get("current_explainer") or "").strip()
    transcript = _resolve_explainer_transcript(connection, room_code, explainer_name)
    if not transcript:
        return None
    word_pool = _word_pool_for_difficulty(difficulty)
    best_match, confidence = _best_transcript_match(transcript, word_pool)

    if best_match:
        normalized_best = _normalize_guess(best_match)
        normalized_current = _normalize_guess(current_word)
        best_is_current = bool(normalized_best and normalized_current and normalized_best == normalized_current)
        if best_is_current:
            chance_to_guess = min(0.94, max(0.36, 0.22 + confidence * 0.78))
            if random.random() <= chance_to_guess:
                return _humanize_bot_guess(current_word)
        elif confidence >= 0.86 and random.random() < 0.48:
            return _humanize_bot_guess(best_match)
        elif confidence >= 0.74 and random.random() < 0.22:
            return _humanize_bot_guess(best_match)

    transcript_tokens = _extract_transcript_tokens(transcript)
    if transcript_tokens and random.random() < 0.22:
        return _humanize_bot_guess(random.choice(transcript_tokens))
    return None


def _pick_wrong_bot_guess(current_word, difficulty):
    current = _normalize_guess(current_word)
    for _ in range(12):
        candidate = _pick_word(difficulty)
        if _normalize_guess(candidate) != current:
            return candidate
    fallback_pool = ["ракета", "лампа", "окно", "музыка", "яблоко", "поезд"]
    for candidate in fallback_pool:
        if _normalize_guess(candidate) != current:
            return candidate
    return "другое"


def _process_room_guess(connection, room_code, player_name, guess):
    room = connection.execute("SELECT * FROM rooms WHERE code = ?", (room_code,)).fetchone()
    if room is None:
        raise ValueError("Room not found.")
    resolved_player_name = _resolve_room_player_name(connection, room_code, player_name)
    if not resolved_player_name:
        raise ValueError("Player is not in this room.")
    if (room["game_phase"] or "lobby").strip().lower() != "round":
        raise ValueError("Round has not started yet.")
    if _same_player_name(resolved_player_name, room["current_explainer"]):
        raise ValueError("Current explainer cannot send guesses.")

    _insert_message(connection, room_code, resolved_player_name, guess, "guess")

    explainer_name = room["current_explainer"]
    current_word = room["current_word"] or ""
    normalized_guess = _normalize_guess(guess)
    normalized_word = _normalize_guess(current_word)
    correct = bool(normalized_guess and normalized_word and normalized_guess == normalized_word)

    awarded_explainer_score = None
    awarded_guesser_score = None
    if correct:
        awarded_explainer_score = _adjust_score(connection, room_code, explainer_name, +1)
        awarded_guesser_score = _adjust_score(connection, room_code, resolved_player_name, +1)
        new_word = _pick_word(room["difficulty"])
        connection.execute(
            """
            UPDATE rooms
            SET current_word = ?,
                updated_at = ?
            WHERE code = ?
            """,
            (new_word, _now(), room_code),
        )
        _insert_message(
            connection,
            room_code,
            "System",
            f"{resolved_player_name} guessed the word. {explainer_name} +1 and {resolved_player_name} +1.",
            "system",
        )
    else:
        _touch_room(connection, room_code)

    response_payload = _room_payload(connection, room_code, player_name=resolved_player_name)
    return {
        "correct": correct,
        "awarded_player": explainer_name if correct else None,
        "awarded_delta": 1 if correct else 0,
        "awarded_score": awarded_explainer_score,
        "guesser_player": resolved_player_name if correct else None,
        "guesser_delta": 1 if correct else 0,
        "guesser_score": awarded_guesser_score,
        "room": response_payload["room"] if response_payload else {},
        "scores": response_payload.get("scores", []) if response_payload else [],
        "current_word": response_payload.get("current_word", "") if response_payload else "",
    }


def _run_bot_activity(connection, room_code):
    players = _room_players(connection, room_code)
    _purge_bots_if_ai_disabled(connection, room_code, players)


def _insert_message(connection, room_code, player_name, message, message_type):
    created_at = _now()
    connection.execute(
        """
        INSERT INTO room_messages (room_code, player_name, message, message_type, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (room_code, player_name, message, message_type, created_at),
    )
    row = connection.execute(
        """
        SELECT id, room_code, player_name, message, message_type, created_at
        FROM room_messages
        WHERE id = last_insert_rowid()
        """
    ).fetchone()
    return _normalize_message(row)


def _ensure_score_row(connection, room_code, player_name):
    connection.execute(
        """
        INSERT OR IGNORE INTO room_scores (room_code, player_name, score, updated_at)
        VALUES (?, ?, 0, ?)
        """,
        (room_code, player_name, _now()),
    )


def _adjust_score(connection, room_code, player_name, delta):
    _ensure_score_row(connection, room_code, player_name)
    connection.execute(
        """
        UPDATE room_scores
        SET score = score + ?,
            updated_at = ?
        WHERE room_code = ? AND player_name = ?
        """,
        (int(delta), _now(), room_code, player_name),
    )
    row = connection.execute(
        """
        SELECT score
        FROM room_scores
        WHERE room_code = ? AND player_name = ?
        """,
        (room_code, player_name),
    ).fetchone()
    return int(row["score"])


def _delete_room(connection, room_code):
    connection.execute("DELETE FROM room_messages WHERE room_code = ?", (room_code,))
    connection.execute("DELETE FROM room_scores WHERE room_code = ?", (room_code,))
    connection.execute("DELETE FROM room_voice_chunks WHERE room_code = ?", (room_code,))
    connection.execute("DELETE FROM room_players WHERE room_code = ?", (room_code,))
    connection.execute("DELETE FROM rooms WHERE code = ?", (room_code,))


def _repair_room_integrity(connection, room_code):
    room = connection.execute("SELECT * FROM rooms WHERE code = ?", (room_code,)).fetchone()
    if room is None:
        return {"deleted": True, "players": []}

    players = _room_players(connection, room_code)
    if _purge_bots_if_ai_disabled(connection, room_code, players):
        players = _room_players(connection, room_code)
    if not players:
        _delete_room(connection, room_code)
        return {"deleted": True, "players": []}

    preferred_human = _preferred_human_player(players)
    host_name = room["host_name"] if room["host_name"] in players else ""
    if not host_name or (_is_bot_player(host_name) and preferred_human and not _is_bot_player(preferred_human)):
        host_name = preferred_human or players[0]

    current_explainer = host_name if host_name in players else ""
    if not current_explainer:
        current_explainer = preferred_human or players[0]

    voice_speaker = room["voice_speaker"] if room["voice_speaker"] in players else None
    voice_until = room["voice_until"] if voice_speaker else None
    explainer_changed = current_explainer != room["current_explainer"]
    current_mic_muted = _normalize_mic_muted_flag(room["explainer_mic_muted"], default=1)
    explainer_mic_muted = 1 if explainer_changed else current_mic_muted

    if (
        host_name != room["host_name"]
        or current_explainer != room["current_explainer"]
        or voice_speaker != room["voice_speaker"]
        or voice_until != room["voice_until"]
        or explainer_mic_muted != current_mic_muted
    ):
        connection.execute(
            """
            UPDATE rooms
            SET host_name = ?,
                current_explainer = ?,
                voice_speaker = ?,
                voice_until = ?,
                explainer_mic_muted = ?,
                updated_at = ?
            WHERE code = ?
            """,
            (host_name, current_explainer, voice_speaker, voice_until, explainer_mic_muted, _now(), room_code),
        )
    return {"deleted": False, "players": players}


def _sync_room_after_player_leave(connection, room_code):
    return _repair_room_integrity(connection, room_code)


def _prune_empty_rooms(connection):
    empty_rows = connection.execute(
        """
        SELECT r.code
        FROM rooms AS r
        LEFT JOIN room_players AS p ON p.room_code = r.code
        GROUP BY r.code
        HAVING COUNT(p.player_name) = 0
        """
    ).fetchall()
    for row in empty_rows:
        _delete_room(connection, row["code"])


def _prune_voice_chunks(connection, room_code, keep_last=200):
    threshold_row = connection.execute(
        """
        SELECT id
        FROM room_voice_chunks
        WHERE room_code = ?
        ORDER BY id DESC
        LIMIT 1 OFFSET ?
        """,
        (room_code, int(keep_last)),
    ).fetchone()
    if threshold_row is None:
        return

    connection.execute(
        """
        DELETE FROM room_voice_chunks
        WHERE room_code = ? AND id < ?
        """,
        (room_code, int(threshold_row["id"])),
    )


def _insert_voice_chunk(connection, room_code, player_name, sample_rate, pcm16_b64):
    connection.execute(
        """
        INSERT INTO room_voice_chunks (room_code, player_name, sample_rate, pcm16_b64, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (room_code, player_name, int(sample_rate), pcm16_b64, _now()),
    )
    row = connection.execute(
        """
        SELECT id
        FROM room_voice_chunks
        WHERE id = last_insert_rowid()
        """
    ).fetchone()
    _prune_voice_chunks(connection, room_code)
    return int(row["id"])


def _start_game_countdown(connection, room_code, started_by, auto_start=False):
    room = connection.execute("SELECT * FROM rooms WHERE code = ?", (room_code,)).fetchone()
    if room is None:
        return False

    phase = (room["game_phase"] or "lobby").strip().lower()
    if phase in {"countdown", "round"}:
        return False

    now_dt = _utc_now()
    countdown_end = now_dt + timedelta(seconds=10)
    round_end = countdown_end + timedelta(seconds=max(20, int(room["round_timer_sec"])))
    players = _room_players(connection, room_code)
    host_name = (room["host_name"] or "").strip()
    preferred_human = _preferred_human_player(players)
    if host_name and host_name in players:
        current_explainer = host_name
    else:
        current_explainer = preferred_human or players[0]

    connection.execute(
        """
        UPDATE rooms
        SET game_phase = 'countdown',
            current_explainer = ?,
            countdown_end_at = ?,
            round_end_at = ?,
            starts_count = starts_count + 1,
            bot_next_action_at = NULL,
            voice_speaker = NULL,
            voice_until = NULL,
            explainer_mic_muted = 1,
            updated_at = ?
        WHERE code = ?
        """,
        (current_explainer, _dt_to_str(countdown_end), _dt_to_str(round_end), _now(), room_code),
    )

    if auto_start:
        message = "Room is full. Game starts in 10 seconds."
    else:
        message = f"{started_by} started the game. 10-second countdown."
    _insert_message(connection, room_code, "System", message, "system")
    return True


def _refresh_room_phase(connection, room_code):
    room = connection.execute("SELECT * FROM rooms WHERE code = ?", (room_code,)).fetchone()
    if room is None:
        return

    phase = (room["game_phase"] or "lobby").strip().lower()
    now_dt = _utc_now()

    if phase == "countdown":
        countdown_end = _str_to_dt(room["countdown_end_at"])
        if countdown_end is not None and now_dt >= countdown_end:
            round_end = _str_to_dt(room["round_end_at"])
            if round_end is None:
                round_end = now_dt + timedelta(seconds=max(20, int(room["round_timer_sec"])))
            connection.execute(
                """
                UPDATE rooms
                SET game_phase = 'round',
                    countdown_end_at = NULL,
                    round_end_at = ?,
                    updated_at = ?
                WHERE code = ?
                """,
                (_dt_to_str(round_end), _now(), room_code),
            )
            _insert_message(connection, room_code, "System", "Round started.", "system")
            return

    if phase == "round":
        round_end = _str_to_dt(room["round_end_at"])
        if round_end is not None and now_dt >= round_end:
            connection.execute(
                """
                UPDATE rooms
                SET game_phase = 'lobby',
                    countdown_end_at = NULL,
                    round_end_at = NULL,
                    bot_next_action_at = NULL,
                    voice_speaker = NULL,
                    voice_until = NULL,
                    explainer_mic_muted = 1,
                    updated_at = ?
                WHERE code = ?
                """,
                (_now(), room_code),
            )
            _insert_message(connection, room_code, "System", "Round time is over.", "system")


def _room_payload(connection, room_code, player_name="", since_id=None):
    _refresh_room_phase(connection, room_code)
    room = _room_with_count(connection, room_code)
    if room is None:
        return None

    players = _room_players(connection, room_code)
    scores = _room_scores(connection, room_code)

    if since_id is not None:
        rows = connection.execute(
            """
            SELECT id, room_code, player_name, message, message_type, created_at
            FROM room_messages
            WHERE room_code = ? AND id > ?
            ORDER BY id ASC
            """,
            (room_code, int(since_id)),
        ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT id, room_code, player_name, message, message_type, created_at
            FROM (
                SELECT id, room_code, player_name, message, message_type, created_at
                FROM room_messages
                WHERE room_code = ?
                ORDER BY id DESC
                LIMIT 80
            )
            ORDER BY id ASC
            """,
            (room_code,),
        ).fetchall()
    messages = [_normalize_message(row) for row in rows]

    can_see_word = bool(player_name) and _same_player_name(player_name, room["current_explainer"])
    explainer_mic_muted = bool(_normalize_mic_muted_flag(room.get("explainer_mic_muted"), default=1))

    if explainer_mic_muted and (room.get("voice_speaker") or room.get("voice_until")):
        connection.execute(
            """
            UPDATE rooms
            SET voice_speaker = NULL,
                voice_until = NULL
            WHERE code = ?
            """,
            (room_code,),
        )
        room["voice_speaker"] = None
        room["voice_until"] = None

    voice_until_dt = _str_to_dt(room.get("voice_until"))
    voice_active = bool(room.get("voice_speaker")) and voice_until_dt is not None and voice_until_dt >= _utc_now()

    if not voice_active and (room.get("voice_speaker") or room.get("voice_until")):
        connection.execute(
            """
            UPDATE rooms
            SET voice_speaker = NULL,
                voice_until = NULL
            WHERE code = ?
            """,
            (room_code,),
        )
        room["voice_speaker"] = None
        room["voice_until"] = None

    room_view = dict(room)
    room_view["explainer_mic_muted"] = explainer_mic_muted
    if not can_see_word:
        room_view["current_word"] = ""

    phase = (room.get("game_phase") or "lobby").strip().lower()
    countdown_left_sec = 0
    round_left_sec = 0
    if phase == "countdown":
        countdown_end_dt = _str_to_dt(room.get("countdown_end_at"))
        if countdown_end_dt is not None:
            countdown_left_sec = max(0, int((countdown_end_dt - _utc_now()).total_seconds() + 0.999))
    elif phase == "round":
        round_end_dt = _str_to_dt(room.get("round_end_at"))
        if round_end_dt is not None:
            round_left_sec = max(0, int((round_end_dt - _utc_now()).total_seconds() + 0.999))

    players_count = int(room.get("players_count") or len(players) or 0)
    required_players = _required_players_to_start(room.get("max_players"))
    is_viewer_player = bool(player_name) and any(_same_player_name(player_name, listed_player) for listed_player in players)
    is_viewer_explainer = bool(player_name) and _same_player_name(player_name, room.get("current_explainer"))
    is_viewer_host = bool(player_name) and _same_player_name(player_name, room.get("host_name"))
    if phase != "round":
        explainer_mic_state = "idle"
    elif explainer_mic_muted:
        explainer_mic_state = "off"
    elif voice_active and _same_player_name(room.get("voice_speaker"), room.get("current_explainer")):
        explainer_mic_state = "speaking"
    else:
        explainer_mic_state = "on"

    return {
        "room": room_view,
        "players": players,
        "scores": scores,
        "messages": messages,
        "voice_active": voice_active,
        "voice_speaker": room.get("voice_speaker") if voice_active else None,
        "explainer_mic_muted": explainer_mic_muted,
        "explainer_mic_state": explainer_mic_state,
        "can_see_word": can_see_word,
        "current_word": room.get("current_word") if can_see_word else "",
        "game_phase": phase,
        "countdown_left_sec": countdown_left_sec,
        "round_left_sec": round_left_sec,
        "viewer": {
            "player_name": player_name,
            "is_player": is_viewer_player,
            "is_explainer": is_viewer_explainer,
            "is_host": is_viewer_host,
            "can_control_start": bool(is_viewer_host and phase == "lobby"),
            "can_start_game": bool(is_viewer_host and phase == "lobby" and players_count >= required_players),
            "can_send_chat": bool(is_viewer_player and not (is_viewer_explainer and phase in {"countdown", "round"})),
            "can_use_voice": bool(is_viewer_explainer and phase == "round"),
            "can_toggle_mic": bool(is_viewer_explainer and phase == "round"),
            "explainer_mic_state": explainer_mic_state,
            "required_players_to_start": required_players,
        },
        "server_time": _now(),
    }


class RoomHandler(BaseHTTPRequestHandler):
    server_version = "AliasRoomServer/1.5"

    def _json_response(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _parse_json_body(self):
        raw_length = self.headers.get("Content-Length", "0").strip() or "0"
        length = int(raw_length)
        if length <= 0:
            return {}

        body = self.rfile.read(length).decode("utf-8")
        try:
            return json.loads(body)
        except json.JSONDecodeError as error:
            raise ValueError("Invalid JSON body.") from error

    def do_GET(self):
        parsed = urlparse(self.path)
        parts = [part for part in parsed.path.split("/") if part]

        if parts == ["health"]:
            self._json_response(200, {"ok": True, "status": "healthy"})
            return

        if parts == ["api", "rooms"]:
            self._handle_list_rooms(parsed.query)
            return

        if parts == ["api", "rooms", "preview-code"]:
            self._handle_preview_room_code()
            return

        if len(parts) == 3 and parts[0] == "api" and parts[1] == "rooms":
            self._handle_get_room(parts[2].upper())
            return

        if len(parts) == 4 and parts[0] == "api" and parts[1] == "rooms" and parts[3] == "state":
            self._handle_room_state(parts[2].upper(), parsed.query)
            return

        if len(parts) == 4 and parts[0] == "api" and parts[1] == "rooms" and parts[3] == "voice-chunks":
            self._handle_voice_chunks(parts[2].upper(), parsed.query)
            return

        if parts == ["api", "auth", "register", "state"]:
            self._handle_auth_register_state(parsed.query)
            return

        if parts == ["api", "auth", "password", "state"]:
            self._handle_auth_password_state(parsed.query)
            return

        self._json_response(404, {"error": "Route not found."})

    def do_POST(self):
        parsed = urlparse(self.path)
        parts = [part for part in parsed.path.split("/") if part]

        if parts == ["api", "rooms"]:
            self._handle_create_room()
            return

        if len(parts) == 4 and parts[0] == "api" and parts[1] == "rooms" and parts[3] == "join":
            self._handle_join_room(parts[2].upper())
            return

        if len(parts) == 4 and parts[0] == "api" and parts[1] == "rooms" and parts[3] == "leave":
            self._handle_leave_room(parts[2].upper())
            return

        if len(parts) == 4 and parts[0] == "api" and parts[1] == "rooms" and parts[3] == "chat":
            self._handle_room_chat(parts[2].upper())
            return

        if len(parts) == 4 and parts[0] == "api" and parts[1] == "rooms" and parts[3] == "guess":
            self._handle_room_guess(parts[2].upper())
            return

        if len(parts) == 4 and parts[0] == "api" and parts[1] == "rooms" and parts[3] == "start-game":
            self._handle_start_game(parts[2].upper())
            return

        if len(parts) == 4 and parts[0] == "api" and parts[1] == "rooms" and parts[3] in {"skip-word", "next-word"}:
            self._handle_skip_word(parts[2].upper())
            return

        if len(parts) == 4 and parts[0] == "api" and parts[1] == "rooms" and parts[3] == "voice-ping":
            self._handle_voice_ping(parts[2].upper())
            return

        if len(parts) == 4 and parts[0] == "api" and parts[1] == "rooms" and parts[3] == "mic-state":
            self._handle_mic_state(parts[2].upper())
            return

        if len(parts) == 4 and parts[0] == "api" and parts[1] == "rooms" and parts[3] == "voice-chunk":
            self._handle_voice_chunk(parts[2].upper())
            return

        if parts == ["api", "auth", "register", "request-code"]:
            self._handle_auth_register_request_code()
            return

        if parts == ["api", "auth", "register", "resend"]:
            self._handle_auth_register_resend()
            return

        if parts == ["api", "auth", "register", "confirm"]:
            self._handle_auth_register_confirm()
            return

        if parts == ["api", "auth", "register", "cancel"]:
            self._handle_auth_register_cancel()
            return

        if parts == ["api", "auth", "password", "request-code"]:
            self._handle_auth_password_request_code()
            return

        if parts == ["api", "auth", "password", "resend"]:
            self._handle_auth_password_resend()
            return

        if parts == ["api", "auth", "password", "confirm"]:
            self._handle_auth_password_confirm()
            return

        if parts == ["api", "auth", "password", "cancel"]:
            self._handle_auth_password_cancel()
            return

        self._json_response(404, {"error": "Route not found."})

    def _session_id_from_query(self, query):
        params = parse_qs(query)
        return (params.get("session_id", [""])[0] or "").strip()

    def _handle_auth_register_request_code(self):
        try:
            payload = self._parse_json_body()
            result = _begin_registration_verification(
                name=payload.get("name"),
                email=payload.get("email"),
                password=payload.get("password"),
                bio=payload.get("bio"),
                avatar_path=payload.get("avatar_path"),
            )
        except ValueError as error:
            self._json_response(400, {"error": str(error)})
            return
        self._json_response(200, result)

    def _handle_auth_register_state(self, query):
        session_id = self._session_id_from_query(query)
        if not session_id:
            self._json_response(400, {"error": "session_id is required."})
            return
        try:
            result = _registration_state(session_id)
        except ValueError as error:
            self._json_response(400, {"error": str(error)})
            return
        self._json_response(200, result)

    def _handle_auth_register_resend(self):
        try:
            payload = self._parse_json_body()
            session_id = (payload.get("session_id") or "").strip()
            if not session_id:
                raise ValueError("session_id is required.")
            result = _resend_registration_code(session_id)
        except ValueError as error:
            self._json_response(400, {"error": str(error)})
            return
        self._json_response(200, result)

    def _handle_auth_register_confirm(self):
        try:
            payload = self._parse_json_body()
            session_id = (payload.get("session_id") or "").strip()
            if not session_id:
                raise ValueError("session_id is required.")
            result = _confirm_registration_code(session_id, payload.get("code"))
        except ValueError as error:
            self._json_response(400, {"error": str(error)})
            return
        self._json_response(200, result)

    def _handle_auth_register_cancel(self):
        try:
            payload = self._parse_json_body()
            session_id = (payload.get("session_id") or "").strip()
            if not session_id:
                raise ValueError("session_id is required.")
            _cancel_registration_session(session_id)
        except ValueError as error:
            self._json_response(400, {"error": str(error)})
            return
        self._json_response(200, {"ok": True})

    def _handle_auth_password_request_code(self):
        try:
            payload = self._parse_json_body()
            result = _begin_password_reset(email=payload.get("email"))
        except ValueError as error:
            self._json_response(400, {"error": str(error)})
            return
        self._json_response(200, result)

    def _handle_auth_password_state(self, query):
        session_id = self._session_id_from_query(query)
        if not session_id:
            self._json_response(400, {"error": "session_id is required."})
            return
        try:
            result = _password_reset_state(session_id)
        except ValueError as error:
            self._json_response(400, {"error": str(error)})
            return
        self._json_response(200, result)

    def _handle_auth_password_resend(self):
        try:
            payload = self._parse_json_body()
            session_id = (payload.get("session_id") or "").strip()
            if not session_id:
                raise ValueError("session_id is required.")
            result = _resend_password_reset_code(session_id)
        except ValueError as error:
            self._json_response(400, {"error": str(error)})
            return
        self._json_response(200, result)

    def _handle_auth_password_confirm(self):
        try:
            payload = self._parse_json_body()
            session_id = (payload.get("session_id") or "").strip()
            if not session_id:
                raise ValueError("session_id is required.")
            result = _confirm_password_reset_code(session_id, payload.get("code"))
        except ValueError as error:
            self._json_response(400, {"error": str(error)})
            return
        self._json_response(200, result)

    def _handle_auth_password_cancel(self):
        try:
            payload = self._parse_json_body()
            session_id = (payload.get("session_id") or "").strip()
            if not session_id:
                raise ValueError("session_id is required.")
            _cancel_password_reset_session(session_id)
        except ValueError as error:
            self._json_response(400, {"error": str(error)})
            return
        self._json_response(200, {"ok": True})

    def _handle_list_rooms(self, query):
        params = parse_qs(query)
        public_only = params.get("public_only", ["1"])[0] == "1"

        with _connect() as connection:
            _prune_empty_rooms(connection)
            room_code_rows = connection.execute("SELECT code FROM rooms").fetchall()
            for room_code_row in room_code_rows:
                _repair_room_integrity(connection, room_code_row["code"])
            if public_only:
                rows = connection.execute(
                    """
                    SELECT r.*, COUNT(p.player_name) AS players_count
                    FROM rooms AS r
                    LEFT JOIN room_players AS p ON p.room_code = r.code
                    WHERE r.visibility_scope = 'public'
                    GROUP BY r.code
                    ORDER BY r.created_at DESC
                    LIMIT 50
                    """
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT r.*, COUNT(p.player_name) AS players_count
                    FROM rooms AS r
                    LEFT JOIN room_players AS p ON p.room_code = r.code
                    GROUP BY r.code
                    ORDER BY r.created_at DESC
                    LIMIT 100
                    """
                ).fetchall()

        rooms = [_normalize_room(row, row["players_count"]) for row in rows]
        for room in rooms:
            room["current_word"] = ""
        self._json_response(200, {"rooms": rooms})

    def _handle_get_room(self, room_code):
        with _connect() as connection:
            _prune_empty_rooms(connection)
            _repair_room_integrity(connection, room_code)
            room = _room_with_count(connection, room_code)
        if room is None:
            self._json_response(404, {"error": "Room not found."})
            return
        room["current_word"] = ""
        self._json_response(200, {"room": room})

    def _handle_preview_room_code(self):
        with _connect() as connection:
            code = _generate_room_code(connection)
        self._json_response(200, {"code": code})

    def _handle_create_room(self):
        try:
            payload = self._parse_json_body()
        except ValueError as error:
            self._json_response(400, {"error": str(error)})
            return

        host_name = (payload.get("host_name") or "").strip()
        room_name = (payload.get("room_name") or "").strip()
        difficulty = (payload.get("difficulty") or "").strip()
        visibility = (payload.get("visibility") or "").strip()
        visibility_scope = _normalize_scope(payload.get("visibility_scope"), visibility)
        requested_code = payload.get("requested_code")
        client_id = _normalize_client_id(payload.get("client_id"))

        try:
            max_players = int(payload.get("max_players"))
            round_timer_sec = int(payload.get("round_timer_sec"))
        except (TypeError, ValueError):
            self._json_response(400, {"error": "Invalid room parameters."})
            return

        if not host_name:
            self._json_response(400, {"error": "Host name is required."})
            return
        if len(room_name) < 3:
            self._json_response(400, {"error": "Room name must be at least 3 characters."})
            return
        if not difficulty:
            self._json_response(400, {"error": "Difficulty is required."})
            return
        if max_players < 2 or max_players > 20:
            self._json_response(400, {"error": "Player count must be between 2 and 20."})
            return
        if round_timer_sec < 20 or round_timer_sec > 300:
            self._json_response(400, {"error": "Round timer must be between 20 and 300 seconds."})
            return

        with _connect() as connection:
            room_code = _resolve_room_code(connection, requested_code if visibility_scope == "private" else None)
            timestamp = _now()
            current_word = _pick_word(difficulty)
            if _rooms_has_legacy_rounds_column(connection):
                connection.execute(
                    """
                    INSERT INTO rooms (
                        code,
                        room_name,
                        host_name,
                        max_players,
                        difficulty,
                        visibility,
                        visibility_scope,
                        round_timer_sec,
                        rounds,
                        current_explainer,
                        current_word,
                        voice_speaker,
                        voice_until,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
                    """,
                    (
                        room_code,
                        room_name,
                        host_name,
                        max_players,
                        difficulty,
                        visibility,
                        visibility_scope,
                        round_timer_sec,
                        1,
                        host_name,
                        current_word,
                        timestamp,
                        timestamp,
                    ),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO rooms (
                        code,
                        room_name,
                        host_name,
                        max_players,
                        difficulty,
                        visibility,
                        visibility_scope,
                        round_timer_sec,
                        current_explainer,
                        current_word,
                        voice_speaker,
                        voice_until,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
                    """,
                    (
                        room_code,
                        room_name,
                        host_name,
                        max_players,
                        difficulty,
                        visibility,
                        visibility_scope,
                        round_timer_sec,
                        host_name,
                        current_word,
                        timestamp,
                        timestamp,
                    ),
                )
            connection.execute(
                """
                INSERT INTO room_players (room_code, player_name, client_id, joined_at)
                VALUES (?, ?, ?, ?)
                """,
                (room_code, host_name, client_id or None, timestamp),
            )
            _ensure_score_row(connection, room_code, host_name)
            _insert_message(connection, room_code, "System", f"{host_name} created the room.", "system")
            room = _room_with_count(connection, room_code)

        room["current_word"] = ""
        self._json_response(201, {"room": room})

    def _handle_join_room(self, room_code):
        try:
            payload = self._parse_json_body()
        except ValueError as error:
            self._json_response(400, {"error": str(error)})
            return

        requested_player_name = (payload.get("player_name") or "").strip()
        guest_requested = bool(payload.get("is_guest"))
        client_id = _normalize_client_id(payload.get("client_id"))
        if not requested_player_name:
            self._json_response(400, {"error": "Player name is required."})
            return

        with _connect() as connection:
            _prune_empty_rooms(connection)
            _refresh_room_phase(connection, room_code)
            _repair_room_integrity(connection, room_code)
            room = connection.execute("SELECT * FROM rooms WHERE code = ?", (room_code,)).fetchone()
            if room is None:
                self._json_response(404, {"error": "Room not found."})
                return

            player_name = requested_player_name
            existing_row = None
            existing_players = connection.execute(
                """
                SELECT player_name, client_id
                FROM room_players
                WHERE room_code = ?
                ORDER BY joined_at ASC, rowid ASC
                """,
                (room_code,),
            ).fetchall()
            requested_normalized = _normalize_player_name(player_name)
            if requested_normalized:
                for row in existing_players:
                    existing_name = (row["player_name"] or "").strip()
                    if _normalize_player_name(existing_name) == requested_normalized:
                        existing_row = row
                        break

            if existing_row is not None:
                existing_player_name = (existing_row["player_name"] or "").strip()
                existing_client_id = _normalize_client_id(existing_row["client_id"])
                same_client = bool(client_id) and bool(existing_client_id) and client_id == existing_client_id

                player_name = existing_player_name or player_name
                if same_client:
                    pass
                elif guest_requested or _is_guest_player_name(player_name):
                    player_name = _next_available_guest_name(connection, room_code, player_name)
                    existing_row = None
                elif client_id and not existing_client_id and not _is_guest_player_name(player_name):
                    connection.execute(
                        """
                        UPDATE room_players
                        SET client_id = ?
                        WHERE room_code = ? AND player_name = ?
                        """,
                        (client_id, room_code, player_name),
                    )
                else:
                    self._json_response(409, {"error": "Player name is already used in this room."})
                    return

            if existing_row is None:
                count_row = connection.execute(
                    "SELECT COUNT(*) AS players_count FROM room_players WHERE room_code = ?",
                    (room_code,),
                ).fetchone()
                players_count = int(count_row["players_count"])
                if players_count >= int(room["max_players"]):
                    self._json_response(409, {"error": "Room is already full."})
                    return

                connection.execute(
                    """
                    INSERT INTO room_players (room_code, player_name, client_id, joined_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (room_code, player_name, client_id or None, _now()),
                )
                _ensure_score_row(connection, room_code, player_name)
                _insert_message(connection, room_code, "System", f"{player_name} joined the room.", "system")

            _touch_room(connection, room_code)
            payload_state = _room_payload(connection, room_code, player_name=player_name)
            room_data = _room_with_count(connection, room_code)

        if room_data:
            room_data["current_word"] = ""

        if payload_state is None:
            self._json_response(
                200,
                {
                    "room": room_data or {},
                    "players": [],
                    "scores": [],
                    "messages": [],
                    "viewer": {
                        "player_name": player_name,
                        "is_player": True,
                        "is_explainer": False,
                        "is_host": False,
                        "can_control_start": False,
                        "can_start_game": False,
                        "can_send_chat": True,
                        "can_use_voice": False,
                        "can_toggle_mic": False,
                        "explainer_mic_state": "idle",
                        "required_players_to_start": 1,
                    },
                    "voice_active": False,
                    "voice_speaker": None,
                    "explainer_mic_muted": True,
                    "explainer_mic_state": "idle",
                    "can_see_word": False,
                    "current_word": "",
                    "game_phase": "lobby",
                    "countdown_left_sec": 0,
                    "round_left_sec": 0,
                    "server_time": _now(),
                    "joined_as": player_name,
                },
            )
            return

        self._json_response(
            200,
            {
                "room": payload_state.get("room", room_data or {}),
                "players": payload_state.get("players", []),
                "scores": payload_state.get("scores", []),
                "messages": payload_state.get("messages", []),
                "viewer": payload_state.get("viewer", {}),
                "voice_active": payload_state.get("voice_active", False),
                "voice_speaker": payload_state.get("voice_speaker"),
                "explainer_mic_muted": payload_state.get("explainer_mic_muted", True),
                "explainer_mic_state": payload_state.get("explainer_mic_state", "idle"),
                "can_see_word": payload_state.get("can_see_word", False),
                "current_word": payload_state.get("current_word", ""),
                "game_phase": payload_state.get("game_phase", "lobby"),
                "countdown_left_sec": payload_state.get("countdown_left_sec", 0),
                "round_left_sec": payload_state.get("round_left_sec", 0),
                "server_time": payload_state.get("server_time", _now()),
                "joined_as": player_name,
            },
        )

    def _handle_leave_room(self, room_code):
        try:
            payload = self._parse_json_body()
        except ValueError as error:
            self._json_response(400, {"error": str(error)})
            return

        player_name = (payload.get("player_name") or "").strip()
        if not player_name:
            self._json_response(400, {"error": "Player name is required."})
            return

        with _connect() as connection:
            room = connection.execute("SELECT * FROM rooms WHERE code = ?", (room_code,)).fetchone()
            if room is None:
                self._json_response(200, {"ok": True, "room_deleted": True, "already_left": True, "players": []})
                return

            resolved_player_name = _resolve_room_player_name(connection, room_code, player_name)
            is_player = bool(resolved_player_name)
            if not is_player:
                room_data = _room_with_count(connection, room_code)
                players = _room_players(connection, room_code)
                self._json_response(
                    200,
                    {
                        "ok": True,
                        "room_deleted": False,
                        "already_left": True,
                        "room": room_data or {},
                        "players": players,
                    },
                )
                return

            connection.execute(
                """
                DELETE FROM room_players
                WHERE room_code = ? AND player_name = ?
                """,
                (room_code, resolved_player_name),
            )
            connection.execute(
                """
                DELETE FROM room_scores
                WHERE room_code = ? AND player_name = ?
                """,
                (room_code, resolved_player_name),
            )
            connection.execute(
                """
                DELETE FROM room_voice_chunks
                WHERE room_code = ? AND player_name = ?
                """,
                (room_code, resolved_player_name),
            )

            leave_state = _sync_room_after_player_leave(connection, room_code)
            if leave_state["deleted"]:
                self._json_response(200, {"ok": True, "room_deleted": True, "players": []})
                return

            _insert_message(connection, room_code, "System", f"{resolved_player_name} left the room.", "system")
            _touch_room(connection, room_code)
            room_data = _room_with_count(connection, room_code)
            players = _room_players(connection, room_code)

        if room_data:
            room_data["current_word"] = ""
        self._json_response(
            200,
            {
                "ok": True,
                "room_deleted": False,
                "room": room_data or {},
                "players": players,
            },
        )

    def _handle_room_state(self, room_code, query):
        params = parse_qs(query)
        player_name = (params.get("player_name", [""])[0] or "").strip()
        since_id = None
        raw_since = (params.get("since_id", [""])[0] or "").strip()
        if raw_since:
            try:
                since_id = int(raw_since)
            except ValueError:
                since_id = None

        with _connect() as connection:
            _prune_empty_rooms(connection)
            repair_state = _repair_room_integrity(connection, room_code)
            if repair_state["deleted"]:
                self._json_response(404, {"error": "Room not found."})
                return
            resolved_player_name = player_name
            if player_name:
                resolved_player_name = _resolve_room_player_name(connection, room_code, player_name)
                if not resolved_player_name:
                    self._json_response(403, {"error": "Player is not in this room."})
                    return
            payload = _room_payload(connection, room_code, player_name=resolved_player_name, since_id=since_id)

        if payload is None:
            self._json_response(404, {"error": "Room not found."})
            return
        self._json_response(200, payload)

    def _handle_room_chat(self, room_code):
        try:
            payload = self._parse_json_body()
        except ValueError as error:
            self._json_response(400, {"error": str(error)})
            return

        player_name = (payload.get("player_name") or "").strip()
        message = (payload.get("message") or "").strip()
        if not player_name:
            self._json_response(400, {"error": "Player name is required."})
            return
        if not message:
            self._json_response(400, {"error": "Message cannot be empty."})
            return
        if len(message) > 240:
            self._json_response(400, {"error": "Message is too long."})
            return

        with _connect() as connection:
            room = connection.execute(
                "SELECT code, current_explainer, game_phase FROM rooms WHERE code = ?",
                (room_code,),
            ).fetchone()
            if room is None:
                self._json_response(404, {"error": "Room not found."})
                return
            resolved_player_name = _resolve_room_player_name(connection, room_code, player_name)
            if not resolved_player_name:
                self._json_response(403, {"error": "Player is not in this room."})
                return
            phase = (room["game_phase"] or "lobby").strip().lower()
            if phase in {"countdown", "round"} and _same_player_name(resolved_player_name, room["current_explainer"]):
                self._json_response(403, {"error": "Current explainer cannot send chat messages."})
                return

            message_row = _insert_message(connection, room_code, resolved_player_name, message, "chat")
            _touch_room(connection, room_code)

        self._json_response(201, {"message": message_row})

    def _handle_room_guess(self, room_code):
        try:
            payload = self._parse_json_body()
        except ValueError as error:
            self._json_response(400, {"error": str(error)})
            return

        player_name = (payload.get("player_name") or "").strip()
        guess = (payload.get("guess") or "").strip()
        if not player_name:
            self._json_response(400, {"error": "Player name is required."})
            return
        if not guess:
            self._json_response(400, {"error": "Guess cannot be empty."})
            return
        if len(guess) > 120:
            self._json_response(400, {"error": "Guess is too long."})
            return

        with _connect() as connection:
            try:
                result = _process_room_guess(connection, room_code, player_name, guess)
            except ValueError as error:
                message = str(error)
                if message == "Room not found.":
                    self._json_response(404, {"error": message})
                elif message in {"Player is not in this room.", "Current explainer cannot send guesses."}:
                    self._json_response(403, {"error": message})
                elif message == "Round has not started yet.":
                    self._json_response(409, {"error": message})
                else:
                    self._json_response(400, {"error": message})
                return

        self._json_response(200, result)

    def _handle_start_game(self, room_code):
        try:
            payload = self._parse_json_body()
        except ValueError as error:
            self._json_response(400, {"error": str(error)})
            return

        player_name = (payload.get("player_name") or "").strip()
        if not player_name:
            self._json_response(400, {"error": "Player name is required."})
            return

        with _connect() as connection:
            _refresh_room_phase(connection, room_code)
            room = connection.execute("SELECT * FROM rooms WHERE code = ?", (room_code,)).fetchone()
            if room is None:
                self._json_response(404, {"error": "Room not found."})
                return

            resolved_player_name = _resolve_room_player_name(connection, room_code, player_name)
            if not resolved_player_name:
                self._json_response(403, {"error": "Player is not in this room."})
                return
            if not _same_player_name(resolved_player_name, room["host_name"]):
                self._json_response(403, {"error": "Only the room host can start the game."})
                return

            players_row = connection.execute(
                "SELECT COUNT(*) AS players_count FROM room_players WHERE room_code = ?",
                (room_code,),
            ).fetchone()
            players_count = int(players_row["players_count"])
            if players_count < 1:
                self._json_response(409, {"error": "Room has no players."})
                return
            phase = (room["game_phase"] or "lobby").strip().lower()
            if phase in {"countdown", "round"}:
                payload = _room_payload(connection, room_code, player_name=resolved_player_name)
                self._json_response(
                    200,
                    {
                        "ok": True,
                        "already_started": True,
                        "room": payload["room"] if payload else {},
                        "players": payload.get("players", []) if payload else [],
                        "scores": payload.get("scores", []) if payload else [],
                        "messages": payload.get("messages", []) if payload else [],
                        "viewer": payload.get("viewer", {}) if payload else {},
                        "voice_active": payload.get("voice_active", False) if payload else False,
                        "voice_speaker": payload.get("voice_speaker") if payload else None,
                        "current_word": payload.get("current_word", "") if payload else "",
                        "game_phase": payload.get("game_phase") if payload else phase,
                        "countdown_left_sec": payload.get("countdown_left_sec", 0) if payload else 0,
                        "round_left_sec": payload.get("round_left_sec", 0) if payload else 0,
                        "server_time": payload.get("server_time") if payload else _now(),
                    },
                )
                return

            _start_game_countdown(connection, room_code, started_by=resolved_player_name, auto_start=False)
            updated = _room_payload(connection, room_code, player_name=resolved_player_name)

        self._json_response(
            200,
            {
                "ok": True,
                "room": updated["room"] if updated else {},
                "players": updated.get("players", []) if updated else [],
                "scores": updated.get("scores", []) if updated else [],
                "messages": updated.get("messages", []) if updated else [],
                "viewer": updated.get("viewer", {}) if updated else {},
                "voice_active": updated.get("voice_active", False) if updated else False,
                "voice_speaker": updated.get("voice_speaker") if updated else None,
                "current_word": updated.get("current_word", "") if updated else "",
                "game_phase": updated.get("game_phase", "countdown") if updated else "countdown",
                "countdown_left_sec": updated.get("countdown_left_sec", 10) if updated else 10,
                "round_left_sec": updated.get("round_left_sec", 0) if updated else 0,
                "server_time": updated.get("server_time") if updated else _now(),
            },
        )

    def _handle_skip_word(self, room_code):
        try:
            payload = self._parse_json_body()
        except ValueError as error:
            self._json_response(400, {"error": str(error)})
            return

        player_name = (payload.get("player_name") or "").strip()
        if not player_name:
            self._json_response(400, {"error": "Player name is required."})
            return

        with _connect() as connection:
            _refresh_room_phase(connection, room_code)
            room = connection.execute("SELECT * FROM rooms WHERE code = ?", (room_code,)).fetchone()
            if room is None:
                self._json_response(404, {"error": "Room not found."})
                return
            resolved_player_name = _resolve_room_player_name(connection, room_code, player_name)
            if not resolved_player_name:
                self._json_response(403, {"error": "Player is not in this room."})
                return
            if not _same_player_name(resolved_player_name, room["current_explainer"]):
                self._json_response(403, {"error": "Only current explainer can skip words."})
                return
            if (room["game_phase"] or "lobby").strip().lower() != "round":
                self._json_response(409, {"error": "Round has not started yet."})
                return

            next_word = _pick_word(room["difficulty"])
            explainer_score = _adjust_score(connection, room_code, resolved_player_name, -1)
            connection.execute(
                """
                UPDATE rooms
                SET current_word = ?,
                    updated_at = ?
                WHERE code = ?
                """,
                (next_word, _now(), room_code),
            )
            _insert_message(connection, room_code, "System", f"{resolved_player_name} skipped word: -1 point.", "system")
            room_payload = _room_payload(connection, room_code, player_name=resolved_player_name)

        self._json_response(
            200,
            {
                "room": room_payload["room"] if room_payload else {},
                "scores": room_payload.get("scores", []) if room_payload else [],
                "current_word": room_payload.get("current_word", "") if room_payload else "",
                "delta": -1,
                "score": explainer_score,
            },
        )

    def _handle_mic_state(self, room_code):
        try:
            payload = self._parse_json_body()
        except ValueError as error:
            self._json_response(400, {"error": str(error)})
            return

        player_name = (payload.get("player_name") or "").strip()
        if not player_name:
            self._json_response(400, {"error": "Player name is required."})
            return

        muted_raw = payload.get("muted")
        if isinstance(muted_raw, bool):
            muted = muted_raw
        elif isinstance(muted_raw, (int, float)):
            muted = bool(int(muted_raw))
        elif isinstance(muted_raw, str):
            muted = muted_raw.strip().lower() in {"1", "true", "yes", "on", "y"}
        else:
            muted = bool(muted_raw)

        with _connect() as connection:
            _refresh_room_phase(connection, room_code)
            room = connection.execute("SELECT * FROM rooms WHERE code = ?", (room_code,)).fetchone()
            if room is None:
                self._json_response(404, {"error": "Room not found."})
                return
            resolved_player_name = _resolve_room_player_name(connection, room_code, player_name)
            if not resolved_player_name:
                self._json_response(403, {"error": "Player is not in this room."})
                return
            if not _same_player_name(resolved_player_name, room["current_explainer"]):
                self._json_response(403, {"error": "Only current explainer can toggle microphone."})
                return
            if (room["game_phase"] or "lobby").strip().lower() != "round":
                self._json_response(409, {"error": "Round has not started yet."})
                return

            if muted:
                connection.execute(
                    """
                    UPDATE rooms
                    SET explainer_mic_muted = 1,
                        voice_speaker = NULL,
                        voice_until = NULL,
                        updated_at = ?
                    WHERE code = ?
                    """,
                    (_now(), room_code),
                )
            else:
                connection.execute(
                    """
                    UPDATE rooms
                    SET explainer_mic_muted = 0,
                        updated_at = ?
                    WHERE code = ?
                    """,
                    (_now(), room_code),
                )

            payload_state = _room_payload(connection, room_code, player_name=resolved_player_name)

        self._json_response(
            200,
            {
                "ok": True,
                "muted": muted,
                "room": payload_state["room"] if payload_state else {},
                "voice_active": payload_state.get("voice_active", False) if payload_state else False,
                "voice_speaker": payload_state.get("voice_speaker") if payload_state else None,
                "explainer_mic_state": payload_state.get("explainer_mic_state", "idle") if payload_state else "idle",
                "server_time": payload_state.get("server_time") if payload_state else _now(),
            },
        )

    def _handle_voice_ping(self, room_code):
        try:
            payload = self._parse_json_body()
        except ValueError as error:
            self._json_response(400, {"error": str(error)})
            return

        player_name = (payload.get("player_name") or "").strip()
        if not player_name:
            self._json_response(400, {"error": "Player name is required."})
            return

        try:
            active_seconds = int(payload.get("active_seconds", 3))
        except (TypeError, ValueError):
            active_seconds = 3
        active_seconds = max(1, min(6, active_seconds))

        with _connect() as connection:
            _refresh_room_phase(connection, room_code)
            room = connection.execute("SELECT * FROM rooms WHERE code = ?", (room_code,)).fetchone()
            if room is None:
                self._json_response(404, {"error": "Room not found."})
                return
            resolved_player_name = _resolve_room_player_name(connection, room_code, player_name)
            if not resolved_player_name:
                self._json_response(403, {"error": "Player is not in this room."})
                return
            if not _same_player_name(resolved_player_name, room["current_explainer"]):
                self._json_response(403, {"error": "Only current explainer can use voice channel."})
                return
            if (room["game_phase"] or "lobby").strip().lower() != "round":
                self._json_response(409, {"error": "Round has not started yet."})
                return

            until = _utc_now() + timedelta(seconds=active_seconds)
            connection.execute(
                """
                UPDATE rooms
                SET voice_speaker = ?,
                    voice_until = ?,
                    explainer_mic_muted = 0,
                    updated_at = ?
                WHERE code = ?
                """,
                (resolved_player_name, _dt_to_str(until), _now(), room_code),
            )

        self._json_response(
            200,
            {
                "ok": True,
                "voice_speaker": resolved_player_name,
                "voice_until": _dt_to_str(until),
            },
        )

    def _handle_voice_chunk(self, room_code):
        try:
            payload = self._parse_json_body()
        except ValueError as error:
            self._json_response(400, {"error": str(error)})
            return

        player_name = (payload.get("player_name") or "").strip()
        pcm16_b64 = (payload.get("pcm16_b64") or "").strip()
        try:
            sample_rate = int(payload.get("sample_rate", 16000))
        except (TypeError, ValueError):
            sample_rate = 16000

        if not player_name:
            self._json_response(400, {"error": "Player name is required."})
            return
        if not pcm16_b64:
            self._json_response(400, {"error": "Voice chunk payload is empty."})
            return
        if len(pcm16_b64) > 20000:
            self._json_response(400, {"error": "Voice chunk is too large."})
            return
        if sample_rate < 8000 or sample_rate > 48000:
            self._json_response(400, {"error": "Unsupported sample rate."})
            return

        with _connect() as connection:
            _refresh_room_phase(connection, room_code)
            room = connection.execute("SELECT * FROM rooms WHERE code = ?", (room_code,)).fetchone()
            if room is None:
                self._json_response(404, {"error": "Room not found."})
                return
            resolved_player_name = _resolve_room_player_name(connection, room_code, player_name)
            if not resolved_player_name:
                self._json_response(403, {"error": "Player is not in this room."})
                return
            if not _same_player_name(resolved_player_name, room["current_explainer"]):
                self._json_response(403, {"error": "Only current explainer can broadcast voice."})
                return
            if (room["game_phase"] or "lobby").strip().lower() != "round":
                self._json_response(409, {"error": "Round has not started yet."})
                return

            chunk_id = _insert_voice_chunk(connection, room_code, resolved_player_name, sample_rate, pcm16_b64)
            _touch_room(connection, room_code)

        self._json_response(201, {"ok": True, "id": chunk_id})

    def _handle_voice_chunks(self, room_code, query):
        params = parse_qs(query)
        player_name = (params.get("player_name", [""])[0] or "").strip()
        raw_since = (params.get("since_id", ["0"])[0] or "0").strip()
        try:
            since_id = int(raw_since)
        except ValueError:
            since_id = 0
        since_id = max(0, since_id)

        if not player_name:
            self._json_response(400, {"error": "Player name is required."})
            return

        with _connect() as connection:
            room = connection.execute("SELECT code FROM rooms WHERE code = ?", (room_code,)).fetchone()
            if room is None:
                self._json_response(404, {"error": "Room not found."})
                return
            resolved_player_name = _resolve_room_player_name(connection, room_code, player_name)
            if not resolved_player_name:
                self._json_response(403, {"error": "Player is not in this room."})
                return

            rows = connection.execute(
                """
                SELECT id, room_code, player_name, sample_rate, pcm16_b64, created_at
                FROM room_voice_chunks
                WHERE room_code = ? AND id > ? AND player_name != ?
                ORDER BY id ASC
                LIMIT 40
                """,
                (room_code, since_id, resolved_player_name),
            ).fetchall()

            max_row = connection.execute(
                """
                SELECT MAX(id) AS max_id
                FROM room_voice_chunks
                WHERE room_code = ?
                """,
                (room_code,),
            ).fetchone()

        chunks = []
        for row in rows:
            chunks.append(
                {
                    "id": int(row["id"]),
                    "room_code": row["room_code"],
                    "player_name": row["player_name"],
                    "sample_rate": int(row["sample_rate"]),
                    "pcm16_b64": row["pcm16_b64"],
                    "created_at": row["created_at"],
                }
            )

        last_id = int(max_row["max_id"]) if max_row and max_row["max_id"] is not None else since_id
        self._json_response(200, {"chunks": chunks, "last_id": last_id})

    def log_message(self, _format, *_args):
        return


def main():
    default_host = os.environ.get("ALIAS_ROOM_SERVER_HOST", "0.0.0.0")
    default_port_raw = os.environ.get("PORT") or os.environ.get("ALIAS_ROOM_SERVER_PORT") or "8765"
    try:
        default_port = int(default_port_raw)
    except ValueError:
        default_port = 8765

    env_db_path = (os.environ.get("ALIAS_ROOMS_DB_PATH") or "").strip()

    parser = argparse.ArgumentParser(description="Alias Online room server")
    parser.add_argument("--host", default=default_host)
    parser.add_argument("--port", type=int, default=default_port)
    parser.add_argument("--db-path", default=env_db_path or None)
    args = parser.parse_args()

    if args.db_path:
        configure_db_path(args.db_path)
    else:
        resolve_db_path()
    _init_db()
    server = ThreadingHTTPServer((args.host, args.port), RoomHandler)
    print(f"Room server started on http://{args.host}:{args.port}")
    server.serve_forever()


def create_server(host="127.0.0.1", port=8765, db_path=None):
    if db_path:
        configure_db_path(db_path)
    else:
        resolve_db_path()
    _init_db()
    return ThreadingHTTPServer((host, int(port)), RoomHandler)


if __name__ == "__main__":
    main()
