import json
import logging
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import suppress
from pathlib import Path
from typing import Any, Dict, Generator, Optional, Tuple, Union

from kivy.app import App
from kivy.utils import platform

from api_client import (
    ApiClient,
    ConnectionError as ApiConnectionError,
    ValidationError,
    ServerError,
)

logger = logging.getLogger(__name__)

from config import (
    DEFAULT_LOCAL_ROOM_SERVER_URL,
    DEFAULT_PUBLIC_ROOM_SERVER_URL,
    REMOTE_WAKE_CACHE_TTL_SECONDS,
    REMOTE_WAKE_TOTAL_TIMEOUT_SECONDS,
    REMOTE_WAKE_PROBE_TIMEOUT_SECONDS,
    REMOTE_GET_ATTEMPTS,
    REMOTE_MUTATION_ATTEMPTS,
)

ROOM_SERVER_URL_ENV = "ALIAS_ROOM_SERVER_URL"
ROOM_SERVER_URL_FILE_ENV = "ALIAS_ROOM_SERVER_URL_FILE"
MOBILE_ROOM_SERVER_URL_ENV = "ALIAS_MOBILE_ROOM_SERVER_URL"
PUBLIC_ROOM_SERVER_URL_ENV = "ALIAS_PUBLIC_ROOM_SERVER_URL"

_cached_room_server_url = None
_remote_wake_cache: Dict[str, float] = {}


def _is_mobile_platform() -> bool:
    """Check if running on Android or iOS."""
    return platform in {"android", "ios"}


def _is_onrender_host(server_url: str) -> bool:
    """Check if URL is hosted on render.com."""
    parsed = urllib.parse.urlparse(_normalize_room_server_url(server_url))
    host = (parsed.hostname or "").strip().lower()
    return host.endswith(".onrender.com")


def _looks_like_cert_error(error: Exception) -> bool:
    """Check if error looks like SSL certificate verification issue."""
    chain = [error]
    reason = getattr(error, "reason", None)
    if reason is not None:
        chain.append(reason)
    for item in chain:
        if isinstance(item, ssl.SSLCertVerificationError):
            return True
        if isinstance(item, ssl.SSLError):
            text = str(item).lower()
            if "certificate" in text or "cert" in text:
                return True
        text = str(item).lower()
        if "certificate verify failed" in text or "ssl: cert" in text:
            return True
    return False


def _urlopen_with_mobile_ssl_fallback(
    request: urllib.request.Request, *, timeout: float, server_url: str
) -> Any:
    """Open URL with SSL verification fallback for mobile/Render."""
    try:
        return urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.URLError as error:
        if _is_mobile_platform() and _is_onrender_host(server_url) and _looks_like_cert_error(error):
            # Use ssl.create_default_context() for unsafe SSL verification (Render self-signed certs)
            import logging
            logger = logging.getLogger(__name__)
            logger.error(
                f"INSECURE: SSL cert verification disabled for {server_url} "
                f"(Render self-signed cert fallback). Error: {error}"
            )
            insecure_context = ssl.create_default_context()
            insecure_context.check_hostname = False
            insecure_context.verify_mode = ssl.CERT_NONE
            return urllib.request.urlopen(request, timeout=timeout, context=insecure_context)
        raise


def _project_root() -> Path:
    """Get project root directory."""
    return Path(__file__).resolve().parent.parent


def _normalize_room_server_url(raw_url: str) -> str:
    """Normalize URL: strip whitespace, add http:// if needed, validate scheme."""
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


def _is_local_url(target_url: str) -> bool:
    """Check if URL points to localhost (127.0.0.1, localhost, ::1)."""
    parsed = urllib.parse.urlparse(_normalize_room_server_url(target_url))
    host = (parsed.hostname or "").strip().lower()
    return host in {"127.0.0.1", "localhost", "::1"}


def _public_room_server_default() -> str:
    """Get default public room server URL from env or config."""
    env_default = _normalize_room_server_url(os.environ.get(PUBLIC_ROOM_SERVER_URL_ENV, ""))
    if env_default:
        return env_default
    return _normalize_room_server_url(DEFAULT_PUBLIC_ROOM_SERVER_URL)


def _candidate_url_files() -> Generator[Path, None, None]:
    """Generate candidate paths for room server URL configuration file."""
    custom_file = (os.environ.get(ROOM_SERVER_URL_FILE_ENV) or "").strip()
    if custom_file:
        yield Path(custom_file).expanduser()

    # Prefer bundled/project config first: it ships with each release.
    yield _project_root() / "data" / "room_server_url.txt"


def _load_url_from_file() -> str:
    """Load room server URL from configuration file."""
    local_fallback = ""
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
                if not _is_local_url(normalized):
                    return normalized
                if not local_fallback:
                    local_fallback = normalized
    return local_fallback


def _resolve_room_server_url() -> str:
    """Resolve room server URL from environment, file, or defaults."""
    from_env = _normalize_room_server_url(os.environ.get(ROOM_SERVER_URL_ENV, ""))
    if from_env:
        return from_env

    from_file = _load_url_from_file()
    if from_file:
        return from_file

    mobile_default = _normalize_room_server_url(os.environ.get(MOBILE_ROOM_SERVER_URL_ENV, ""))
    if mobile_default:
        return mobile_default

    public_default = _public_room_server_default()
    if public_default:
        return public_default

    return DEFAULT_LOCAL_ROOM_SERVER_URL


def room_server_url(refresh: bool = False) -> str:
    """Get cached room server URL, resolving it if needed."""
    global _cached_room_server_url
    if refresh or not _cached_room_server_url:
        _cached_room_server_url = _resolve_room_server_url()
    return _cached_room_server_url


def set_room_server_url(new_url: str) -> str:
    """Set room server URL after normalization and validation."""
    global _cached_room_server_url
    normalized = _normalize_room_server_url(new_url)
    if not normalized:
        raise ValueError("Некорректный URL сервера комнат.")
    _cached_room_server_url = normalized
    return _cached_room_server_url


def is_local_room_server_url(url: Optional[str] = None) -> bool:
    """Check if given URL (or current server URL) is local."""
    target_url = _normalize_room_server_url(url or room_server_url())
    return _is_local_url(target_url)


def room_server_bind_params(url: Optional[str] = None) -> Tuple[str, int]:
    """Get (host, port) tuple for raw socket operations."""
    target_url = _normalize_room_server_url(url or room_server_url())
    parsed = urllib.parse.urlparse(target_url)
    host = (parsed.hostname or "127.0.0.1").strip().lower()
    if host in {"localhost", "::1"}:
        host = "127.0.0.1"
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    return host, int(port)


def _ensure_remote_server_awake(server_url: str) -> bool:
    """Polling health check to warm up remote Render server (best effort with caching)."""
    normalized = _normalize_room_server_url(server_url)
    if not normalized or _is_local_url(normalized):
        return True

    now = time.time()
    cached_until = float(_remote_wake_cache.get(normalized, 0.0) or 0.0)
    if now < cached_until:
        return True

    health_url = f"{normalized}/health"
    deadline = now + (REMOTE_WAKE_TOTAL_TIMEOUT_SECONDS if platform in {"android", "ios"} else 35)
    last_error = None
    while time.time() < deadline:
        request = urllib.request.Request(health_url, headers={"Accept": "application/json"}, method="GET")
        try:
            with _urlopen_with_mobile_ssl_fallback(
                request,
                timeout=REMOTE_WAKE_PROBE_TIMEOUT_SECONDS,
                server_url=normalized,
            ) as response:
                if int(getattr(response, "status", 200)) < 500:
                    _remote_wake_cache[normalized] = time.time() + REMOTE_WAKE_CACHE_TTL_SECONDS
                    return True
        except urllib.error.HTTPError as error:
            if int(getattr(error, "code", 500)) < 500:
                _remote_wake_cache[normalized] = time.time() + REMOTE_WAKE_CACHE_TTL_SECONDS
                return True
            last_error = error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            last_error = error
        time.sleep(1.3)

    return False if last_error is not None else False


def _parse_request_path(path: str) -> Tuple[str, Optional[Dict[str, str]]]:
    """Parse path into endpoint and query parameters for GET requests."""
    if "?" not in path:
        return path, None
    endpoint, query_string = path.split("?", 1)
    params = {}
    for key_value in query_string.split("&"):
        if "=" in key_value:
            key, value = key_value.split("=", 1)
            params[urllib.parse.unquote(key)] = urllib.parse.unquote(value)
    return endpoint, params if params else None


def _map_connection_error(
    api_error: Exception, is_local_server: bool, original_error: Optional[Exception] = None
) -> ConnectionError:
    """Map ApiClient exceptions to platform-specific ConnectionError with appropriate message."""
    platform_mobile = platform in ("android", "ios")
    if platform_mobile:
        if is_local_server:
            msg = "Не удалось подключиться к комнатам. Проверь интернет и перезапусти приложение."
        else:
            msg = "Не удалось подключиться к серверу комнат. Проверь интернет и адрес сервера."
    else:
        msg = "Не удалось подключиться к серверу комнат. Проверь интернет и запусти server/room_server.py."
    return ConnectionError(msg) from original_error


def _request_json(
    method: str,
    path: str,
    payload: Optional[Dict[str, Any]] = None,
    timeout: float = 7,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute JSON HTTP request with retry, fallback, and local server handling."""
    server_url = _normalize_room_server_url(base_url or room_server_url())
    if not server_url:
        raise ConnectionError("URL сервера комнат не настроен.")

    local_room_server = is_local_room_server_url(server_url)

    # Pre-request: ensure local server is ready (blocking check)
    if local_room_server:
        app = App.get_running_app()
        ensure_server_ready = getattr(app, "ensure_local_room_server_ready", None) if app is not None else None
        if callable(ensure_server_ready):
            try:
                ready = bool(ensure_server_ready(timeout=4.5))
            except Exception:
                ready = False
            if not ready:
                raise ConnectionError("Не удалось запустить локальный сервер комнат. Перезапусти приложение.")

    # Warm-up remote server (best effort, non-blocking)
    if not local_room_server:
        _ensure_remote_server_awake(server_url)

    # Calculate timeouts and retry attempts based on platform and local/remote
    method_name = method.upper().strip()
    calculated_timeout = timeout if timeout is not None else 7.0

    if platform in {"android", "ios"}:
        calculated_timeout = max(9, int(calculated_timeout))

    if local_room_server:
        calculated_timeout = min(float(calculated_timeout), 4.5)
    else:
        if platform in {"android", "ios"}:
            calculated_timeout = max(float(calculated_timeout), 22.0)
        else:
            calculated_timeout = max(float(calculated_timeout), 15.0)

    # Determine max retries based on method and local/remote
    if method_name == "GET":
        max_retries = REMOTE_GET_ATTEMPTS
    else:
        max_retries = REMOTE_MUTATION_ATTEMPTS

    if local_room_server:
        max_retries = 2

    # Create API client with calculated timeout
    client = ApiClient(base_url=server_url, max_retries=max_retries, timeout=calculated_timeout)

    # Execute request
    last_transport_error = None
    try:
        if method_name == "GET":
            endpoint, params = _parse_request_path(path)
            response = client.get(endpoint, params=params)
        else:
            response = client.post(path, data=payload, is_mutation=(method_name != "GET"))
        return response

    except ApiConnectionError as e:
        last_transport_error = e
        # Try fallback to public server if we haven't already and it's not local
        if base_url is None and not local_room_server:
            fallback_url = _public_room_server_default()
            if fallback_url and fallback_url != server_url:
                try:
                    response = _request_json(
                        method,
                        path,
                        payload=payload,
                        timeout=timeout,
                        base_url=fallback_url,
                    )
                    set_room_server_url(fallback_url)
                    return response
                except Exception:
                    pass

        raise _map_connection_error(e, local_room_server, e)

    except (ValidationError, ServerError) as e:
        # 4xx/5xx errors from server - convert to ValueError with message
        raise ValueError(e.message) from e


def generate_room_code_preview(*, base_url: Optional[str] = None) -> str:
    """Generate a preview of a random room code.

    Returns:
        A random room code (uppercase alphanumeric string)

    Raises:
        ValueError: If server returns invalid response
        ConnectionError: If unable to reach server
    """
    response = _request_json("GET", "/api/rooms/preview-code", base_url=base_url)
    return (response.get("code") or "").strip().upper()


def create_online_room(
    *,
    host_name: str,
    room_name: str,
    max_players: int,
    difficulty: str,
    visibility: str,
    visibility_scope: str,
    round_timer_sec: int,
    client_id: Optional[str] = None,
    requested_code: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new online room with specified configuration.

    Args:
        host_name: Display name of the room host
        room_name: Display name for the room
        max_players: Maximum number of players allowed (1-24)
        difficulty: Game difficulty level
        visibility: Room visibility setting (public/private)
        visibility_scope: Scope of visibility for the room
        round_timer_sec: Round duration in seconds
        client_id: Optional client identifier for tracking
        requested_code: Optional specific room code to request
        base_url: Optional override for server base URL (for testing)

    Returns:
        Dictionary containing room data

    Raises:
        ValueError: If room creation fails (invalid parameters or server rejects)
        ConnectionError: If unable to reach server
    """
    payload = {
        "host_name": host_name,
        "room_name": room_name,
        "max_players": int(max_players),
        "difficulty": difficulty,
        "visibility": visibility,
        "visibility_scope": visibility_scope,
        "round_timer_sec": int(round_timer_sec),
    }
    if client_id:
        payload["client_id"] = str(client_id).strip()
    if requested_code:
        payload["requested_code"] = str(requested_code).strip().upper()
    response = _request_json("POST", "/api/rooms", payload=payload, base_url=base_url)
    return response.get("room", {})


def list_online_rooms(*, public_only: bool = True, base_url: Optional[str] = None) -> list:
    """List online rooms with optional filtering by visibility.

    Args:
        public_only: If True, return only public rooms; if False, include all rooms
        base_url: Optional override for server base URL (for testing)

    Returns:
        List of room dictionaries

    Raises:
        ValueError: If server returns invalid response
        ConnectionError: If unable to reach server
    """
    query = urllib.parse.urlencode({"public_only": "1" if public_only else "0"})
    response = _request_json("GET", f"/api/rooms?{query}", base_url=base_url)
    return response.get("rooms", [])


def join_online_room(
    *,
    room_code: str,
    player_name: str,
    is_guest: bool = False,
    client_id: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Join an existing online room.

    Args:
        room_code: Code of the room to join
        player_name: Display name for the player
        is_guest: If True, join as guest without authentication
        client_id: Optional client identifier for tracking
        base_url: Optional override for server base URL (for testing)

    Returns:
        Dictionary containing room data and initial state

    Raises:
        ValueError: If join fails (room not found, full, etc.)
        ConnectionError: If unable to reach server
    """
    payload = {"player_name": player_name, "is_guest": bool(is_guest)}
    if client_id:
        payload["client_id"] = str(client_id).strip()
    response = _request_json(
        "POST",
        f"/api/rooms/{urllib.parse.quote(room_code)}/join",
        payload=payload,
        base_url=base_url,
    )
    room = dict(response.get("room", {}) or {})
    joined_as = (response.get("joined_as") or "").strip()
    if not joined_as:
        viewer = response.get("viewer")
        if isinstance(viewer, dict):
            joined_as = (viewer.get("player_name") or "").strip()
    state_keys = (
        "room",
        "players",
        "scores",
        "messages",
        "viewer",
        "voice_active",
        "voice_speaker",
        "explainer_mic_muted",
        "explainer_mic_state",
        "can_see_word",
        "current_word",
        "game_phase",
        "countdown_left_sec",
        "round_left_sec",
        "server_time",
    )
    server_state = {}
    for key in state_keys:
        if key in response:
            server_state[key] = response.get(key)
    if not joined_as and client_id:
        try:
            probe_state = get_online_room_state(
                room_code=room_code,
                player_name=player_name,
                client_id=client_id,
                timeout=4,
                base_url=base_url,
            )
            if isinstance(probe_state, dict):
                probe_viewer = probe_state.get("viewer")
                if isinstance(probe_viewer, dict):
                    joined_as = (probe_viewer.get("player_name") or "").strip()
                for key in state_keys:
                    if key in probe_state and key not in server_state:
                        server_state[key] = probe_state.get(key)
        except Exception:
            pass
    if joined_as:
        room["_joined_as"] = joined_as
    if server_state:
        if not isinstance(server_state.get("room"), dict):
            server_state["room"] = dict(room)
        room["_server_state"] = server_state
    return room


def leave_online_room(
    *, room_code: str, player_name: str, client_id: Optional[str] = None, base_url: Optional[str] = None
) -> Dict[str, Any]:
    """Leave an online room.

    Args:
        room_code: Code of the room to leave
        player_name: Name of the player leaving
        client_id: Optional client identifier for tracking
        base_url: Optional override for server base URL (for testing)

    Returns:
        Server response dictionary

    Raises:
        ValueError: If leave fails
        ConnectionError: If unable to reach server
    """
    payload = {"player_name": player_name}
    if client_id:
        payload["client_id"] = str(client_id).strip()
    return _request_json(
        "POST",
        f"/api/rooms/{urllib.parse.quote(room_code)}/leave",
        payload=payload,
        base_url=base_url,
    )


def get_online_room(*, room_code: str, base_url: Optional[str] = None) -> Dict[str, Any]:
    """Get room data by code.

    Args:
        room_code: Code of the room to fetch
        base_url: Optional override for server base URL (for testing)

    Returns:
        Dictionary containing room data

    Raises:
        ValueError: If room not found
        ConnectionError: If unable to reach server
    """
    response = _request_json("GET", f"/api/rooms/{urllib.parse.quote(room_code)}", base_url=base_url)
    return response.get("room", {})


def get_online_room_state(
    *,
    room_code: str,
    player_name: str,
    since_id: Optional[int] = None,
    timeout: float = 6,
    client_id: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Get room state with optional filtering by message ID.

    Args:
        room_code: Code of the room
        player_name: Name of the requesting player
        since_id: Optional message ID to fetch updates since (for polling)
        timeout: Request timeout in seconds
        client_id: Optional client identifier for tracking
        base_url: Optional override for server base URL (for testing)

    Returns:
        Dictionary containing full room state

    Raises:
        ValueError: If server returns invalid response
        ConnectionError: If unable to reach server
    """
    query_payload = {"player_name": player_name}
    if client_id:
        query_payload["client_id"] = str(client_id).strip()
    if since_id is not None:
        query_payload["since_id"] = str(int(since_id))

    query = urllib.parse.urlencode(query_payload)
    response = _request_json(
        "GET",
        f"/api/rooms/{urllib.parse.quote(room_code)}/state?{query}",
        timeout=timeout,
        base_url=base_url,
    )
    return response


def send_room_chat(
    *, room_code: str, player_name: str, message: str, client_id: Optional[str] = None, base_url: Optional[str] = None
) -> Dict[str, Any]:
    """Send a chat message in a room (guessers only).

    Args:
        room_code: Code of the room
        player_name: Name of the player sending message
        message: Message text
        client_id: Optional client identifier for tracking
        base_url: Optional override for server base URL (for testing)

    Returns:
        Dictionary containing the sent message data

    Raises:
        ValueError: If message send fails (player is explainer, wrong game state, etc.)
        ConnectionError: If unable to reach server
    """
    payload = {"player_name": player_name, "message": message}
    if client_id:
        payload["client_id"] = str(client_id).strip()
    response = _request_json(
        "POST",
        f"/api/rooms/{urllib.parse.quote(room_code)}/chat",
        payload=payload,
        base_url=base_url,
    )
    return response.get("message", {})


def send_room_guess(
    *, room_code: str, player_name: str, guess: str, client_id: Optional[str] = None, base_url: Optional[str] = None
) -> Dict[str, Any]:
    """Submit a guess for the current word (guessers only).

    Args:
        room_code: Code of the room
        player_name: Name of the player guessing
        guess: The guessed word
        client_id: Optional client identifier for tracking
        base_url: Optional override for server base URL (for testing)

    Returns:
        Server response dictionary

    Raises:
        ValueError: If guess fails
        ConnectionError: If unable to reach server
    """
    payload = {"player_name": player_name, "guess": guess}
    if client_id:
        payload["client_id"] = str(client_id).strip()
    return _request_json(
        "POST",
        f"/api/rooms/{urllib.parse.quote(room_code)}/guess",
        payload=payload,
        base_url=base_url,
    )


def start_room_game(
    *, room_code: str, player_name: str, client_id: Optional[str] = None, base_url: Optional[str] = None
) -> Dict[str, Any]:
    """Start the game in a room (host only).

    Args:
        room_code: Code of the room
        player_name: Name of the host starting the game
        client_id: Optional client identifier for tracking
        base_url: Optional override for server base URL (for testing)

    Returns:
        Server response with updated room state

    Raises:
        ValueError: If start fails (not host, already started, etc.)
        ConnectionError: If unable to reach server
    """
    payload = {"player_name": player_name}
    if client_id:
        payload["client_id"] = str(client_id).strip()
    return _request_json(
        "POST",
        f"/api/rooms/{urllib.parse.quote(room_code)}/start-game",
        payload=payload,
        base_url=base_url,
    )


def skip_room_word(
    *, room_code: str, player_name: str, client_id: Optional[str] = None, base_url: Optional[str] = None
) -> Dict[str, Any]:
    """Skip the current word and move to next (explainer only).

    Args:
        room_code: Code of the room
        player_name: Name of the explainer skipping
        client_id: Optional client identifier for tracking
        base_url: Optional override for server base URL (for testing)

    Returns:
        Server response with next word and updated state

    Raises:
        ValueError: If skip fails
        ConnectionError: If unable to reach server
    """
    payload = {"player_name": player_name}
    if client_id:
        payload["client_id"] = str(client_id).strip()
    response = _request_json(
        "POST",
        f"/api/rooms/{urllib.parse.quote(room_code)}/skip-word",
        payload=payload,
        base_url=base_url,
    )
    return response


def next_room_word(
    *, room_code: str, player_name: str, base_url: Optional[str] = None
) -> Dict[str, Any]:
    """Alias for skip_room_word (move to next word).

    Args:
        room_code: Code of the room
        player_name: Name of the explainer
        base_url: Optional override for server base URL (for testing)

    Returns:
        Server response with next word and updated state

    Raises:
        ValueError: If operation fails
        ConnectionError: If unable to reach server
    """
    return skip_room_word(room_code=room_code, player_name=player_name, base_url=base_url)


def ping_room_voice(
    *,
    room_code: str,
    player_name: str,
    active_seconds: int = 3,
    client_id: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Ping voice activity (indicate speaker is active).

    Args:
        room_code: Code of the room
        player_name: Name of the player
        active_seconds: How long the voice activity should be considered active
        client_id: Optional client identifier for tracking
        base_url: Optional override for server base URL (for testing)

    Returns:
        Server response dictionary

    Raises:
        ValueError: If ping fails
        ConnectionError: If unable to reach server
    """
    payload = {"player_name": player_name, "active_seconds": int(active_seconds)}
    if client_id:
        payload["client_id"] = str(client_id).strip()
    return _request_json(
        "POST",
        f"/api/rooms/{urllib.parse.quote(room_code)}/voice-ping",
        payload=payload,
        base_url=base_url,
    )


def set_room_mic_state(
    *, room_code: str, player_name: str, muted: bool, client_id: Optional[str] = None, base_url: Optional[str] = None
) -> Dict[str, Any]:
    """Set microphone mute state for a player.

    Args:
        room_code: Code of the room
        player_name: Name of the player
        muted: True to mute, False to unmute
        client_id: Optional client identifier for tracking
        base_url: Optional override for server base URL (for testing)

    Returns:
        Server response dictionary

    Raises:
        ValueError: If operation fails
        ConnectionError: If unable to reach server
    """
    payload = {"player_name": player_name, "muted": bool(muted)}
    if client_id:
        payload["client_id"] = str(client_id).strip()
    return _request_json(
        "POST",
        f"/api/rooms/{urllib.parse.quote(room_code)}/mic-state",
        payload=payload,
        base_url=base_url,
    )


def send_room_voice_chunk(
    *,
    room_code: str,
    player_name: str,
    pcm16_b64: str,
    sample_rate: int = 16000,
    client_id: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Upload a voice audio chunk (base64-encoded PCM16).

    Args:
        room_code: Code of the room
        player_name: Name of the player sending audio
        pcm16_b64: Base64-encoded PCM16 audio data
        sample_rate: Sample rate of audio (default 16000 Hz)
        client_id: Optional client identifier for tracking
        base_url: Optional override for server base URL (for testing)

    Returns:
        Server response dictionary

    Raises:
        ValueError: If upload fails
        ConnectionError: If unable to reach server
    """
    payload = {
        "player_name": player_name,
        "pcm16_b64": pcm16_b64,
        "sample_rate": int(sample_rate),
    }
    if client_id:
        payload["client_id"] = str(client_id).strip()
    return _request_json(
        "POST",
        f"/api/rooms/{urllib.parse.quote(room_code)}/voice-chunk",
        payload=payload,
        base_url=base_url,
    )


def get_room_voice_chunks(
    *,
    room_code: str,
    player_name: str,
    since_id: int = 0,
    client_id: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch voice audio chunks from other players (optional filtering by ID).

    Args:
        room_code: Code of the room
        player_name: Name of the requesting player
        since_id: Optional message ID to fetch chunks since (for polling)
        client_id: Optional client identifier for tracking
        base_url: Optional override for server base URL (for testing)

    Returns:
        Dictionary containing voice chunks and metadata

    Raises:
        ValueError: If fetch fails
        ConnectionError: If unable to reach server
    """
    query_payload = {
        "player_name": player_name,
        "since_id": str(int(since_id)),
    }
    if client_id:
        query_payload["client_id"] = str(client_id).strip()
    query = urllib.parse.urlencode(query_payload)
    return _request_json(
        "GET",
        f"/api/rooms/{urllib.parse.quote(room_code)}/voice-chunks?{query}",
        base_url=base_url,
    )
