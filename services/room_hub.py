import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from kivy.app import App
from kivy.utils import platform

DEFAULT_LOCAL_ROOM_SERVER_URL = "http://127.0.0.1:8765"
ROOM_SERVER_URL_ENV = "ALIAS_ROOM_SERVER_URL"
ROOM_SERVER_URL_FILE_ENV = "ALIAS_ROOM_SERVER_URL_FILE"
MOBILE_ROOM_SERVER_URL_ENV = "ALIAS_MOBILE_ROOM_SERVER_URL"

_cached_room_server_url = None


def _project_root():
    return Path(__file__).resolve().parent.parent


def _normalize_room_server_url(raw_url):
    clean_url = (raw_url or "").strip().rstrip("/")
    if not clean_url:
        return ""

    candidate = clean_url if "://" in clean_url else f"http://{clean_url}"
    parsed = urllib.parse.urlparse(candidate)
    if not parsed.scheme or not parsed.netloc:
        return ""

    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        return ""

    return f"{scheme}://{parsed.netloc}"


def _candidate_url_files():
    custom_file = (os.environ.get(ROOM_SERVER_URL_FILE_ENV) or "").strip()
    if custom_file:
        yield Path(custom_file).expanduser()

    app = App.get_running_app()
    user_data_dir = getattr(app, "user_data_dir", None) if app is not None else None
    if user_data_dir:
        yield Path(user_data_dir) / "room_server_url.txt"

    yield _project_root() / "data" / "room_server_url.txt"


def _load_url_from_file():
    for config_path in _candidate_url_files():
        if not config_path.exists():
            continue
        try:
            text = config_path.read_text(encoding="utf-8")
        except OSError:
            continue

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            normalized = _normalize_room_server_url(line)
            if normalized:
                return normalized
    return ""


def _resolve_room_server_url():
    from_env = _normalize_room_server_url(os.environ.get(ROOM_SERVER_URL_ENV, ""))
    if from_env:
        return from_env

    from_file = _load_url_from_file()
    if from_file:
        return from_file

    if platform in {"android", "ios"}:
        mobile_default = _normalize_room_server_url(os.environ.get(MOBILE_ROOM_SERVER_URL_ENV, ""))
        if mobile_default:
            return mobile_default
        # Fallback to embedded local room server when public backend is not configured.
        return DEFAULT_LOCAL_ROOM_SERVER_URL

    return DEFAULT_LOCAL_ROOM_SERVER_URL


def room_server_url(refresh=False):
    global _cached_room_server_url
    if refresh or not _cached_room_server_url:
        _cached_room_server_url = _resolve_room_server_url()
    return _cached_room_server_url


def set_room_server_url(new_url):
    global _cached_room_server_url
    normalized = _normalize_room_server_url(new_url)
    if not normalized:
        raise ValueError("Некорректный URL сервера комнат.")
    _cached_room_server_url = normalized
    return _cached_room_server_url


def is_local_room_server_url(url=None):
    target_url = _normalize_room_server_url(url or room_server_url())
    parsed = urllib.parse.urlparse(target_url)
    host = (parsed.hostname or "").strip().lower()
    return host in {"127.0.0.1", "localhost", "::1"}


def room_server_bind_params(url=None):
    target_url = _normalize_room_server_url(url or room_server_url())
    parsed = urllib.parse.urlparse(target_url)
    host = (parsed.hostname or "127.0.0.1").strip().lower()
    if host in {"localhost", "::1"}:
        host = "127.0.0.1"
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    return host, int(port)


def generate_room_code_preview(*, base_url=None):
    response = _request_json("GET", "/api/rooms/preview-code", base_url=base_url)
    return (response.get("code") or "").strip().upper()


def _request_json(method, path, payload=None, timeout=7, base_url=None):
    server_url = _normalize_room_server_url(base_url or room_server_url())
    if not server_url:
        raise ConnectionError("URL сервера комнат не настроен.")

    if is_local_room_server_url(server_url):
        app = App.get_running_app()
        ensure_server_ready = getattr(app, "ensure_local_room_server_ready", None) if app is not None else None
        if callable(ensure_server_ready):
            try:
                ensure_server_ready(timeout=2.8)
            except Exception:
                pass

    url = f"{server_url}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"

    attempts = 3 if method.upper() == "GET" else 1
    request_timeout = timeout if timeout is not None else 7
    if platform in {"android", "ios"}:
        request_timeout = max(9, int(request_timeout))

    body = ""
    last_transport_error = None
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=request_timeout) as response:
                body = response.read().decode("utf-8")
            last_transport_error = None
            break
        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="ignore")
            try:
                parsed = json.loads(details)
            except json.JSONDecodeError:
                parsed = None
            message = parsed.get("error") if isinstance(parsed, dict) else f"HTTP {error.code}"
            raise ValueError(message) from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            last_transport_error = error
            if attempt < attempts:
                time.sleep(0.25 * attempt)
                continue

    if last_transport_error is not None:
        if platform in ("android", "ios"):
            if is_local_room_server_url(server_url):
                raise ConnectionError(
                    "Не удалось подключиться к комнатам. Проверь интернет и перезапусти приложение."
                ) from last_transport_error
            raise ConnectionError(
                "Не удалось подключиться к серверу комнат. Проверь интернет и адрес сервера."
            ) from last_transport_error
        raise ConnectionError(
            "Не удалось подключиться к серверу комнат. Проверь интернет и запусти server/room_server.py."
        ) from last_transport_error

    try:
        return json.loads(body) if body else {}
    except json.JSONDecodeError as error:
        raise ValueError("Сервер комнат вернул некорректный ответ.") from error


def create_online_room(
    *,
    host_name,
    room_name,
    max_players,
    difficulty,
    visibility,
    visibility_scope,
    round_timer_sec,
    requested_code=None,
    base_url=None,
):
    payload = {
        "host_name": host_name,
        "room_name": room_name,
        "max_players": int(max_players),
        "difficulty": difficulty,
        "visibility": visibility,
        "visibility_scope": visibility_scope,
        "round_timer_sec": int(round_timer_sec),
    }
    if requested_code:
        payload["requested_code"] = str(requested_code).strip().upper()
    response = _request_json("POST", "/api/rooms", payload=payload, base_url=base_url)
    return response.get("room", {})


def list_online_rooms(*, public_only=True, base_url=None):
    query = urllib.parse.urlencode({"public_only": "1" if public_only else "0"})
    response = _request_json("GET", f"/api/rooms?{query}", base_url=base_url)
    return response.get("rooms", [])


def join_online_room(*, room_code, player_name, base_url=None):
    payload = {"player_name": player_name}
    response = _request_json(
        "POST",
        f"/api/rooms/{urllib.parse.quote(room_code)}/join",
        payload=payload,
        base_url=base_url,
    )
    return response.get("room", {})


def leave_online_room(*, room_code, player_name, base_url=None):
    payload = {"player_name": player_name}
    return _request_json(
        "POST",
        f"/api/rooms/{urllib.parse.quote(room_code)}/leave",
        payload=payload,
        base_url=base_url,
    )


def get_online_room(*, room_code, base_url=None):
    response = _request_json("GET", f"/api/rooms/{urllib.parse.quote(room_code)}", base_url=base_url)
    return response.get("room", {})


def get_online_room_state(*, room_code, player_name, since_id=None, base_url=None):
    query_payload = {"player_name": player_name}
    if since_id is not None:
        query_payload["since_id"] = str(int(since_id))

    query = urllib.parse.urlencode(query_payload)
    response = _request_json(
        "GET",
        f"/api/rooms/{urllib.parse.quote(room_code)}/state?{query}",
        base_url=base_url,
    )
    return response


def send_room_chat(*, room_code, player_name, message, base_url=None):
    payload = {"player_name": player_name, "message": message}
    response = _request_json(
        "POST",
        f"/api/rooms/{urllib.parse.quote(room_code)}/chat",
        payload=payload,
        base_url=base_url,
    )
    return response.get("message", {})


def send_room_guess(*, room_code, player_name, guess, base_url=None):
    payload = {"player_name": player_name, "guess": guess}
    return _request_json(
        "POST",
        f"/api/rooms/{urllib.parse.quote(room_code)}/guess",
        payload=payload,
        base_url=base_url,
    )


def start_room_game(*, room_code, player_name, base_url=None):
    payload = {"player_name": player_name}
    return _request_json(
        "POST",
        f"/api/rooms/{urllib.parse.quote(room_code)}/start-game",
        payload=payload,
        base_url=base_url,
    )


def skip_room_word(*, room_code, player_name, base_url=None):
    payload = {"player_name": player_name}
    response = _request_json(
        "POST",
        f"/api/rooms/{urllib.parse.quote(room_code)}/skip-word",
        payload=payload,
        base_url=base_url,
    )
    return response


def next_room_word(*, room_code, player_name, base_url=None):
    return skip_room_word(room_code=room_code, player_name=player_name, base_url=base_url)


def ping_room_voice(*, room_code, player_name, active_seconds=3, base_url=None):
    payload = {"player_name": player_name, "active_seconds": int(active_seconds)}
    return _request_json(
        "POST",
        f"/api/rooms/{urllib.parse.quote(room_code)}/voice-ping",
        payload=payload,
        base_url=base_url,
    )


def send_room_voice_chunk(*, room_code, player_name, pcm16_b64, sample_rate=16000, base_url=None):
    payload = {
        "player_name": player_name,
        "pcm16_b64": pcm16_b64,
        "sample_rate": int(sample_rate),
    }
    return _request_json(
        "POST",
        f"/api/rooms/{urllib.parse.quote(room_code)}/voice-chunk",
        payload=payload,
        base_url=base_url,
    )


def get_room_voice_chunks(*, room_code, player_name, since_id=0, base_url=None):
    query = urllib.parse.urlencode(
        {
            "player_name": player_name,
            "since_id": str(int(since_id)),
        }
    )
    return _request_json(
        "GET",
        f"/api/rooms/{urllib.parse.quote(room_code)}/voice-chunks?{query}",
        base_url=base_url,
    )
