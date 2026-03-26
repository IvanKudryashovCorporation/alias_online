import argparse
import json
import os
import random
import sqlite3
import string
from contextlib import suppress
from datetime import datetime, timedelta
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


def configure_db_path(path):
    global DB_PATH
    DB_PATH = Path(path).expanduser()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return DB_PATH


def _resolve_mobile_storage_dir():
    with suppress(Exception):
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
                countdown_end_at TEXT,
                round_end_at TEXT,
                bot_next_action_at TEXT,
                voice_speaker TEXT,
                voice_until TEXT,
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
            ("countdown_end_at", "TEXT"),
            ("round_end_at", "TEXT"),
            ("bot_next_action_at", "TEXT"),
            ("voice_speaker", "TEXT"),
            ("voice_until", "TEXT"),
        ]
        for name, definition in required_columns:
            if name not in existing_columns:
                connection.execute(f"ALTER TABLE rooms ADD COLUMN {name} {definition}")

        room_rows = connection.execute(
            """
            SELECT code, visibility, visibility_scope, host_name, difficulty, current_explainer, current_word, game_phase
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
            connection.execute(
                """
                UPDATE rooms
                SET visibility_scope = ?,
                    current_explainer = ?,
                    current_word = ?,
                    game_phase = ?
                WHERE code = ?
                """,
                (scope, explainer, word, phase, row["code"]),
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
            CREATE INDEX IF NOT EXISTS idx_room_voice_chunks_room_id
            ON room_voice_chunks(room_code, id)
            """
        )


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
        "countdown_end_at": row["countdown_end_at"],
        "round_end_at": row["round_end_at"],
        "bot_next_action_at": row["bot_next_action_at"],
        "voice_speaker": row["voice_speaker"],
        "voice_until": row["voice_until"],
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
    row = connection.execute(
        """
        SELECT 1
        FROM room_players
        WHERE room_code = ? AND player_name = ?
        """,
        (room_code, player_name),
    ).fetchone()
    return row is not None


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
    normalized = (player_name or "").strip().lower()
    return normalized.startswith("bot ")


def _pick_bot_delay_seconds():
    return random.uniform(1.6, 4.2)


def _next_bot_action_at():
    return _dt_to_str(_utc_now() + timedelta(seconds=_pick_bot_delay_seconds()))


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
    if not _is_room_player(connection, room_code, player_name):
        raise ValueError("Player is not in this room.")
    if (room["game_phase"] or "lobby").strip().lower() != "round":
        raise ValueError("Round has not started yet.")
    if player_name == (room["current_explainer"] or "").strip():
        raise ValueError("Current explainer cannot send guesses.")

    _insert_message(connection, room_code, player_name, guess, "guess")

    explainer_name = room["current_explainer"]
    current_word = room["current_word"] or ""
    normalized_guess = _normalize_guess(guess)
    normalized_word = _normalize_guess(current_word)
    correct = bool(normalized_guess and normalized_word and normalized_guess == normalized_word)

    awarded_explainer_score = None
    awarded_guesser_score = None
    if correct:
        awarded_explainer_score = _adjust_score(connection, room_code, explainer_name, +1)
        awarded_guesser_score = _adjust_score(connection, room_code, player_name, +1)
        new_word = _pick_word(room["difficulty"])
        connection.execute(
            """
            UPDATE rooms
            SET current_word = ?,
                bot_next_action_at = ?,
                updated_at = ?
            WHERE code = ?
            """,
            (new_word, _next_bot_action_at(), _now(), room_code),
        )
        _insert_message(
            connection,
            room_code,
            "System",
            f"{player_name} guessed the word. {explainer_name} +1 and {player_name} +1.",
            "system",
        )
    else:
        connection.execute(
            """
            UPDATE rooms
            SET bot_next_action_at = ?,
                updated_at = ?
            WHERE code = ?
            """,
            (_next_bot_action_at(), _now(), room_code),
        )

    response_payload = _room_payload(connection, room_code, player_name=player_name)
    return {
        "correct": correct,
        "awarded_player": explainer_name if correct else None,
        "awarded_delta": 1 if correct else 0,
        "awarded_score": awarded_explainer_score,
        "guesser_player": player_name if correct else None,
        "guesser_delta": 1 if correct else 0,
        "guesser_score": awarded_guesser_score,
        "room": response_payload["room"] if response_payload else {},
        "scores": response_payload.get("scores", []) if response_payload else [],
        "current_word": response_payload.get("current_word", "") if response_payload else "",
    }


def _run_bot_activity(connection, room_code):
    room = connection.execute("SELECT * FROM rooms WHERE code = ?", (room_code,)).fetchone()
    if room is None:
        return

    phase = (room["game_phase"] or "lobby").strip().lower()
    if phase != "round":
        return

    scheduled_at = _str_to_dt(room["bot_next_action_at"])
    if scheduled_at is not None and scheduled_at > _utc_now():
        return

    players = _room_players(connection, room_code)
    bot_players = [player for player in players if _is_bot_player(player) and player != (room["current_explainer"] or "").strip()]
    if not bot_players:
        return

    actor = random.choice(bot_players)
    if random.random() < 0.38:
        guess_text = room["current_word"] or _pick_word(room["difficulty"])
    else:
        guess_text = _pick_wrong_bot_guess(room["current_word"], room["difficulty"])

    try:
        _process_room_guess(connection, room_code, actor, guess_text)
    except ValueError:
        connection.execute(
            """
            UPDATE rooms
            SET bot_next_action_at = ?,
                updated_at = ?
            WHERE code = ?
            """,
            (_next_bot_action_at(), _now(), room_code),
        )


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
    if not players:
        _delete_room(connection, room_code)
        return {"deleted": True, "players": []}

    host_name = room["host_name"] if room["host_name"] in players else players[0]
    current_explainer = room["current_explainer"] if room["current_explainer"] in players else host_name
    voice_speaker = room["voice_speaker"] if room["voice_speaker"] in players else None
    voice_until = room["voice_until"] if voice_speaker else None

    if (
        host_name != room["host_name"]
        or current_explainer != room["current_explainer"]
        or voice_speaker != room["voice_speaker"]
        or voice_until != room["voice_until"]
    ):
        connection.execute(
            """
            UPDATE rooms
            SET host_name = ?,
                current_explainer = ?,
                voice_speaker = ?,
                voice_until = ?,
                updated_at = ?
            WHERE code = ?
            """,
            (host_name, current_explainer, voice_speaker, voice_until, _now(), room_code),
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

    connection.execute(
        """
        UPDATE rooms
        SET game_phase = 'countdown',
            countdown_end_at = ?,
            round_end_at = ?,
            bot_next_action_at = NULL,
            voice_speaker = NULL,
            voice_until = NULL,
            updated_at = ?
        WHERE code = ?
        """,
        (_dt_to_str(countdown_end), _dt_to_str(round_end), _now(), room_code),
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
                    bot_next_action_at = ?,
                    updated_at = ?
                WHERE code = ?
                """,
                (_dt_to_str(round_end), _next_bot_action_at(), _now(), room_code),
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
                    updated_at = ?
                WHERE code = ?
                """,
                (_now(), room_code),
            )
            _insert_message(connection, room_code, "System", "Round time is over.", "system")


def _room_payload(connection, room_code, player_name="", since_id=None):
    _refresh_room_phase(connection, room_code)
    _run_bot_activity(connection, room_code)
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

    can_see_word = bool(player_name) and player_name == room["current_explainer"]
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
    is_viewer_player = bool(player_name) and any(player_name == listed_player for listed_player in players)
    is_viewer_explainer = bool(player_name) and player_name == room.get("current_explainer")
    is_viewer_host = bool(player_name) and player_name == room.get("host_name")

    return {
        "room": room_view,
        "players": players,
        "scores": scores,
        "messages": messages,
        "voice_active": voice_active,
        "voice_speaker": room.get("voice_speaker") if voice_active else None,
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
            "can_control_start": bool(is_viewer_explainer and phase == "lobby"),
            "can_start_game": bool(is_viewer_explainer and phase == "lobby" and players_count >= required_players),
            "can_send_chat": bool(is_viewer_player and not (is_viewer_explainer and phase in {"countdown", "round"})),
            "can_use_voice": bool(is_viewer_explainer and phase == "round"),
            "required_players_to_start": required_players,
        },
        "server_time": _now(),
    }


class RoomHandler(BaseHTTPRequestHandler):
    server_version = "AliasRoomServer/1.4"

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

        if len(parts) == 4 and parts[0] == "api" and parts[1] == "rooms" and parts[3] == "voice-chunk":
            self._handle_voice_chunk(parts[2].upper())
            return

        self._json_response(404, {"error": "Route not found."})

    def _handle_list_rooms(self, query):
        params = parse_qs(query)
        public_only = params.get("public_only", ["1"])[0] == "1"

        with _connect() as connection:
            _prune_empty_rooms(connection)
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
                INSERT INTO room_players (room_code, player_name, joined_at)
                VALUES (?, ?, ?)
                """,
                (room_code, host_name, timestamp),
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

        player_name = (payload.get("player_name") or "").strip()
        if not player_name:
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

            exists = connection.execute(
                """
                SELECT 1
                FROM room_players
                WHERE room_code = ? AND player_name = ?
                """,
                (room_code, player_name),
            ).fetchone()

            if exists is None:
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
                    INSERT INTO room_players (room_code, player_name, joined_at)
                    VALUES (?, ?, ?)
                    """,
                    (room_code, player_name, _now()),
                )
                _ensure_score_row(connection, room_code, player_name)
                _insert_message(connection, room_code, "System", f"{player_name} joined the room.", "system")

            _touch_room(connection, room_code)
            room_data = _room_with_count(connection, room_code)

        room_data["current_word"] = ""
        self._json_response(200, {"room": room_data})

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

            is_player = _is_room_player(connection, room_code, player_name)
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
                (room_code, player_name),
            )
            connection.execute(
                """
                DELETE FROM room_scores
                WHERE room_code = ? AND player_name = ?
                """,
                (room_code, player_name),
            )
            connection.execute(
                """
                DELETE FROM room_voice_chunks
                WHERE room_code = ? AND player_name = ?
                """,
                (room_code, player_name),
            )

            leave_state = _sync_room_after_player_leave(connection, room_code)
            if leave_state["deleted"]:
                self._json_response(200, {"ok": True, "room_deleted": True, "players": []})
                return

            _insert_message(connection, room_code, "System", f"{player_name} left the room.", "system")
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
            if player_name and not _is_room_player(connection, room_code, player_name):
                self._json_response(403, {"error": "Player is not in this room."})
                return
            payload = _room_payload(connection, room_code, player_name=player_name, since_id=since_id)

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
            if not _is_room_player(connection, room_code, player_name):
                self._json_response(403, {"error": "Player is not in this room."})
                return
            phase = (room["game_phase"] or "lobby").strip().lower()
            if phase in {"countdown", "round"} and player_name == (room["current_explainer"] or "").strip():
                self._json_response(403, {"error": "Current explainer cannot send chat messages."})
                return

            message_row = _insert_message(connection, room_code, player_name, message, "chat")
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

            if not _is_room_player(connection, room_code, player_name):
                self._json_response(403, {"error": "Player is not in this room."})
                return
            if player_name != (room["current_explainer"] or "").strip():
                self._json_response(403, {"error": "Only the current explainer can start the game."})
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
                payload = _room_payload(connection, room_code, player_name=player_name)
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

            _start_game_countdown(connection, room_code, started_by=player_name, auto_start=False)
            updated = _room_payload(connection, room_code, player_name=player_name)

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
            if player_name != room["current_explainer"]:
                self._json_response(403, {"error": "Only current explainer can skip words."})
                return
            if (room["game_phase"] or "lobby").strip().lower() != "round":
                self._json_response(409, {"error": "Round has not started yet."})
                return

            next_word = _pick_word(room["difficulty"])
            explainer_score = _adjust_score(connection, room_code, player_name, -1)
            connection.execute(
                """
                UPDATE rooms
                SET current_word = ?,
                    updated_at = ?
                WHERE code = ?
                """,
                (next_word, _now(), room_code),
            )
            _insert_message(connection, room_code, "System", f"{player_name} skipped word: -1 point.", "system")
            room_payload = _room_payload(connection, room_code, player_name=player_name)

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
            if not _is_room_player(connection, room_code, player_name):
                self._json_response(403, {"error": "Player is not in this room."})
                return
            if player_name != room["current_explainer"]:
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
                    updated_at = ?
                WHERE code = ?
                """,
                (player_name, _dt_to_str(until), _now(), room_code),
            )

        self._json_response(
            200,
            {
                "ok": True,
                "voice_speaker": player_name,
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
            if not _is_room_player(connection, room_code, player_name):
                self._json_response(403, {"error": "Player is not in this room."})
                return
            if player_name != room["current_explainer"]:
                self._json_response(403, {"error": "Only current explainer can broadcast voice."})
                return
            if (room["game_phase"] or "lobby").strip().lower() != "round":
                self._json_response(409, {"error": "Round has not started yet."})
                return

            chunk_id = _insert_voice_chunk(connection, room_code, player_name, sample_rate, pcm16_b64)
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
            if not _is_room_player(connection, room_code, player_name):
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
                (room_code, since_id, player_name),
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
