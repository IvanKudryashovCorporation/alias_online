import json
import os
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_ROOM_SERVER_URL = os.environ.get("ALIAS_ROOM_SERVER_URL", "http://127.0.0.1:8765").rstrip("/")


def room_server_url():
    return DEFAULT_ROOM_SERVER_URL


def _request_json(method, path, payload=None, timeout=7, base_url=None):
    server_url = (base_url or DEFAULT_ROOM_SERVER_URL).rstrip("/")
    url = f"{server_url}{path}"

    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="ignore")
        try:
            parsed = json.loads(details)
        except json.JSONDecodeError:
            parsed = None
        message = parsed.get("error") if isinstance(parsed, dict) else f"HTTP {error.code}"
        raise ValueError(message) from error
    except urllib.error.URLError as error:
        raise ConnectionError(
            "Не удалось подключиться к серверу комнат. Проверь интернет и запусти server/room_server.py."
        ) from error

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
    rounds,
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
        "rounds": int(rounds),
    }
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
    # Legacy alias: old callers use next_room_word, but backend now treats it as skip.
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
