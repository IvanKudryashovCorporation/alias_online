import argparse
import sys
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server.room_server import create_server
from services.profile_store import add_friend, initialize_database, list_friend_profiles, save_profile
from services.room_hub import (
    create_online_room,
    get_online_room,
    get_online_room_state,
    join_online_room,
    leave_online_room,
    list_online_rooms,
    send_room_chat,
    send_room_guess,
    skip_room_word,
    start_room_game,
)


def _print_ok(message: str) -> None:
    print(f"[OK] {message}")


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_smoke(project_root: Path, room_port: int) -> None:
    data_dir = project_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    room_db = data_dir / "_qa_smoke_rooms.db"
    profile_db = data_dir / "_qa_smoke_profiles.db"
    for db_path in (room_db, profile_db):
        if db_path.exists():
            db_path.unlink()

    base_url = f"http://127.0.0.1:{room_port}"
    server = create_server(host="127.0.0.1", port=room_port, db_path=room_db)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True, name="qa-smoke-room-server")
    server_thread.start()

    try:
        room = create_online_room(
            host_name="SmokeHost",
            room_name="Smoke Room",
            max_players=6,
            difficulty="Легкие",
            visibility="Публичная",
            visibility_scope="public",
            round_timer_sec=60,
            base_url=base_url,
        )
        room_code = room.get("code", "")
        _assert(bool(room_code), "Room creation returned empty code.")
        _print_ok(f"room created: {room_code}")

        join_online_room(room_code=room_code, player_name="Player1", base_url=base_url)
        join_online_room(room_code=room_code, player_name="Player2", base_url=base_url)
        room_state = get_online_room(room_code=room_code, base_url=base_url)
        _assert(int(room_state.get("players_count") or 0) >= 3, "Players did not join the room.")
        _print_ok("join flow")

        guest_room = create_online_room(
            host_name="Гость1",
            room_name="Guest Naming Room",
            max_players=4,
            difficulty="Легкие",
            visibility="Публичная",
            visibility_scope="public",
            round_timer_sec=45,
            client_id="guest-client-a",
            base_url=base_url,
        )
        guest_room_code = guest_room.get("code", "")
        _assert(bool(guest_room_code), "Guest room code is empty.")
        joined_guest = join_online_room(
            room_code=guest_room_code,
            player_name="Гость1",
            is_guest=True,
            client_id="guest-client-b",
            base_url=base_url,
        )
        joined_as = (joined_guest.get("_joined_as") or "").strip()
        _assert(joined_as and joined_as != "Гость1", "Guest duplicate name was not remapped by server.")
        host_state = get_online_room_state(room_code=guest_room_code, player_name="Гость1", base_url=base_url)
        join_state = get_online_room_state(room_code=guest_room_code, player_name=joined_as, base_url=base_url)
        _assert(bool((host_state.get("viewer") or {}).get("is_host")), "Host viewer role mismatch.")
        _assert(not bool((join_state.get("viewer") or {}).get("is_host")), "Joiner should not become host.")
        _print_ok("guest naming + role sync")

        start_room_game(room_code=room_code, player_name="SmokeHost", base_url=base_url)
        _print_ok("start game request")

        for _ in range(15):
            state = get_online_room_state(room_code=room_code, player_name="SmokeHost", base_url=base_url)
            phase = ((state.get("room") or {}).get("game_phase") or "").lower()
            if phase == "round":
                break
            time.sleep(1)

        state = get_online_room_state(room_code=room_code, player_name="SmokeHost", base_url=base_url)
        room_data = state.get("room") or {}
        _assert((room_data.get("game_phase") or "").lower() == "round", "Room did not reach round phase.")
        explainer = room_data.get("current_explainer") or room_data.get("host_name")
        current_word = room_data.get("current_word") or ""
        _assert(bool(current_word), "Current explainer word is empty.")
        _print_ok("round state")

        guesser = "Player1" if explainer != "Player1" else "Player2"
        send_room_guess(room_code=room_code, player_name=guesser, guess=current_word, base_url=base_url)
        updated = get_online_room_state(room_code=room_code, player_name=guesser, base_url=base_url)
        scores = {row.get("player_name"): int(row.get("score", 0)) for row in (updated.get("scores") or [])}
        _assert(scores.get(explainer, 0) >= 1, "Explainer did not receive +1 for correct guess.")
        _assert(scores.get(guesser, 0) >= 1, "Guesser did not receive +1 for correct guess.")
        _print_ok("scoring")

        chat_msg = send_room_chat(room_code=room_code, player_name=guesser, message="smoke-chat", base_url=base_url)
        _assert((chat_msg.get("message") or "") == "smoke-chat", "Chat message payload mismatch.")
        _print_ok("chat")

        skip_room_word(room_code=room_code, player_name=explainer, base_url=base_url)
        _print_ok("skip word")

        transfer_room = create_online_room(
            host_name="HostA",
            room_name="Transfer Room",
            max_players=6,
            difficulty="Средние",
            visibility="Публичная",
            visibility_scope="public",
            round_timer_sec=45,
            base_url=base_url,
        )
        transfer_code = transfer_room.get("code", "")
        _assert(bool(transfer_code), "Transfer room code is empty.")
        join_online_room(room_code=transfer_code, player_name="JoinB", base_url=base_url)
        join_online_room(room_code=transfer_code, player_name="JoinC", base_url=base_url)
        leave_online_room(room_code=transfer_code, player_name="HostA", base_url=base_url)
        transfer_state = get_online_room(room_code=transfer_code, base_url=base_url)
        _assert((transfer_state.get("host_name") or "") == "JoinB", "Host transfer failed.")
        _print_ok("host transfer")

        leave_online_room(room_code=transfer_code, player_name="JoinB", base_url=base_url)
        leave_online_room(room_code=transfer_code, player_name="JoinC", base_url=base_url)
        rooms = list_online_rooms(public_only=True, base_url=base_url)
        room_codes = {row.get("code") for row in rooms}
        _assert(transfer_code not in room_codes, "Empty room was not removed.")
        _print_ok("empty room cleanup")

        initialize_database(db_path=profile_db)
        profile_a = save_profile(name="SmokeUserA", email="smokea@example.com", password="Secret123", db_path=profile_db)
        profile_b = save_profile(name="SmokeUserB", email="smokeb@example.com", password="Secret123", db_path=profile_db)
        add_friend(profile_a.email, profile_b.email, db_path=profile_db)
        friends = list_friend_profiles(profile_a.email, db_path=profile_db)
        _assert(bool(friends) and friends[0].email == profile_b.email, "Friend query failed.")
        _print_ok("friends profile query")

        print("\n[SMOKE_DESKTOP] PASS")
    finally:
        server.shutdown()
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Alias Online desktop smoke suite")
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--room-port", type=int, default=8897)
    args = parser.parse_args()
    run_smoke(Path(args.project_root), args.room_port)


if __name__ == "__main__":
    main()
