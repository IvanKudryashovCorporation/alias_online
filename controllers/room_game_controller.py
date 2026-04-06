"""Game state management and transitions for room."""

import time
from threading import Thread
from kivy.clock import Clock
from kivy.app import App

from services import ROOM_CREATION_COST, start_room_game


class RoomGameController:
    """Manages game state, transitions, and start logic."""

    def __init__(self, screen):
        self.screen = screen
        self._start_game_request_token = 0
        self._start_game_request_in_flight = False
        self._last_start_attempt_ts = 0.0
        self._start_game_watchdog_event = None
        self._local_starts_count = 0

    def can_start_game(self) -> bool:
        """Check if current player can start the game."""
        viewer = self.screen._viewer_state()
        if viewer and "can_start_game" in viewer:
            return bool(viewer.get("can_start_game"))
        return False

    def can_control_start(self) -> bool:
        """Check if current player can control game start (host in lobby)."""
        viewer = self.screen._viewer_state()
        if viewer and "can_control_start" in viewer:
            return bool(viewer.get("can_control_start"))
        return False

    def is_host(self) -> bool:
        """Check if current player is the host."""
        viewer = self.screen._viewer_state()
        if viewer and "is_host" in viewer:
            return bool(viewer.get("is_host"))
        return False

    def queue_start_game(self):
        """Throttled start game request."""
        now_ts = time.time()
        if self._start_game_request_in_flight or now_ts - self._last_start_attempt_ts < 0.35:
            return
        self._last_start_attempt_ts = now_ts
        self.start_game()

    def start_game(self):
        """Initiate game start sequence."""
        print(f"[START_GAME] Clicked. Current phase: {self.screen._current_phase()}")
        if self.screen._current_phase() != "lobby":
            self.screen.status_label.color = self.screen.COLORS["warning"]
            self.screen.status_label.text = "Игра уже запущена."
            print(f"[START_GAME] BLOCKED - phase is not lobby")
            return

        # Keep action gate aligned with button visibility/source-of-truth from server.
        # If the server says start is allowed (`can_start_game`), do not block locally by a stricter flag.
        if not self.can_start_game():
            self.screen.status_label.color = self.screen.COLORS["warning"]
            self.screen.status_label.text = "Сейчас сервер не разрешает старт игры. Обнови состояние комнаты."
            return

        player_name = self.screen._player_name()
        if not player_name or not self.screen.room_code:
            self.screen.status_label.color = self.screen.COLORS["error"]
            self.screen.status_label.text = "Не удалось определить игрока для старта игры."
            return

        # Calculate if we need to charge coins
        room_before_start = self.screen.room_state.get("room", {})
        try:
            starts_before = int((room_before_start or {}).get("starts_count") or 0)
        except (TypeError, ValueError):
            starts_before = 0
        starts_before = max(starts_before, int(self._local_starts_count or 0))
        should_charge_by_local_state = starts_before >= 1

        # Check if player has enough coins
        if should_charge_by_local_state:
            app = App.get_running_app()
            profile = app.current_profile() if app is not None and getattr(app, "authenticated", False) else None

            if profile is not None:
                try:
                    current_coins = int(getattr(profile, "alias_coins", 0) or 0)
                except (TypeError, ValueError):
                    current_coins = 0
                if current_coins < ROOM_CREATION_COST:
                    self.screen.status_label.color = self.screen.COLORS["warning"]
                    self.screen.status_label.text = (
                        f"Нужно минимум {ROOM_CREATION_COST} AC для запуска игры. Сейчас: {current_coins} AC."
                    )
                    return
            elif app is not None and getattr(app, "guest_mode", False):
                current_coins = int(app.current_alias_coins() or 0)
                if current_coins < ROOM_CREATION_COST:
                    self.screen.status_label.color = self.screen.COLORS["warning"]
                    self.screen.status_label.text = (
                        f"Нужно минимум {ROOM_CREATION_COST} AC для запуска игры. Сейчас: {current_coins} AC."
                    )
                    return

        # Send start request
        self._start_game_request_token += 1
        request_token = self._start_game_request_token
        self._start_game_request_in_flight = True
        self.screen._start_game_request_in_flight = True
        self.screen.start_game_btn.disabled = True
        self.screen.loading_overlay.show("Запускаем игру...")
        self._arm_start_watchdog(request_token)

        Thread(
            target=self._start_game_worker,
            args=(request_token, self.screen.room_code, player_name, self.screen._client_id(), starts_before, should_charge_by_local_state),
            daemon=True,
        ).start()

    def _start_game_worker(self, request_token, room_code, player_name, client_id, starts_before, should_charge_by_local_state):
        """Background worker for game start request."""
        payload = {
            "token": request_token,
            "status": "error",
            "message": "Не удалось запустить игру.",
            "starts_before": int(starts_before or 0),
            "should_charge_by_local_state": bool(should_charge_by_local_state),
        }
        try:
            start_response = start_room_game(
                room_code=room_code,
                player_name=player_name,
                client_id=(client_id or "").strip(),
            )
            payload = {
                "token": request_token,
                "status": "success",
                "start_response": start_response,
                "starts_before": int(starts_before or 0),
                "should_charge_by_local_state": bool(should_charge_by_local_state),
            }
        except ConnectionError as error:
            payload["status"] = "connection_error"
            payload["message"] = str(error)
        except ValueError as error:
            payload["status"] = "value_error"
            payload["message"] = str(error)
        except Exception as error:
            payload["status"] = "error"
            payload["message"] = str(error)

        Clock.schedule_once(lambda _dt, data=payload: self.finish_start_game(data), 0)

    def finish_start_game(self, payload):
        """Handle game start response."""
        try:
            token = int(payload.get("token") or 0)
            print(f"[FINISH_START_GAME] Response arrived. Status: {payload.get('status')}")
            if token != self._start_game_request_token:
                print(f"[FINISH_START_GAME] Token mismatch: {token} != {self._start_game_request_token}")
                return

            self._cancel_start_watchdog()
            if self.screen.manager is None or self.screen.manager.current != self.screen.name:
                print(f"[FINISH_START_GAME] Screen not active")
                return

            status = payload.get("status")
            if status != "success":
                print(f"[FINISH_START_GAME] ERROR - {status}: {payload.get('message')}")
                self.screen.loading_overlay.hide()
                self.screen.start_game_btn.disabled = not self.can_start_game()
                self.screen.status_label.color = self.screen.COLORS["warning"] if status == "value_error" else self.screen.COLORS["error"]
                self.screen.status_label.text = payload.get("message") or "Не удалось запустить игру."
                return

            start_response = payload.get("start_response")
            starts_before = int(payload.get("starts_before") or 0)
            should_charge_by_local_state = bool(payload.get("should_charge_by_local_state"))

            # Update room state with new game state
            updated_state = dict(self.screen.room_state or {})
            if isinstance(start_response, dict):
                for key in (
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
                    "server_time",
                ):
                    if key in start_response:
                        updated_state[key] = start_response.get(key)
                phase = (start_response.get("game_phase") or updated_state.get("game_phase") or "").strip().lower()
                if phase in {"lobby", "countdown", "round"}:
                    updated_state["game_phase"] = phase
                if "countdown_left_sec" in start_response:
                    updated_state["countdown_left_sec"] = int(start_response.get("countdown_left_sec") or 0)
                if "round_left_sec" in start_response:
                    updated_state["round_left_sec"] = int(start_response.get("round_left_sec") or 0)

            old_phase = self.screen._current_phase()
            self.screen.room_state = updated_state
            # Track state version to prevent polling from overwriting with old state
            room_data = updated_state.get("room", {})
            if isinstance(room_data, dict):
                self.screen._room_state_version = (room_data.get("updated_at") or "")
            new_phase = updated_state.get("game_phase", "?")
            print(f"[FINISH_START_GAME] Phase: {old_phase} -> {new_phase}, Version: {self.screen._room_state_version}")
            self.screen._apply_state()
            print(f"[FINISH_START_GAME] After _apply_state(): current phase is {self.screen._current_phase()}")

            room_payload = updated_state.get("room") if isinstance(updated_state, dict) else {}
            try:
                starts_count = int((room_payload or {}).get("starts_count") or 0)
            except (TypeError, ValueError):
                starts_count = 0
            self._local_starts_count = max(starts_count, starts_before + 1)
            self.screen._local_starts_count = self._local_starts_count

            should_charge_start = starts_count > 1 or should_charge_by_local_state
            charge_payload = None
            if should_charge_start:
                charged, charge_payload = self.screen._charge_start_cost()
                if not charged:
                    self.screen.loading_overlay.hide()
                    self.screen.status_label.color = self.screen.COLORS["warning"]
                    self.screen.status_label.text = str(charge_payload)
                    return

            self.screen.loading_overlay.hide()
        finally:
            self._start_game_request_in_flight = False
            self.screen._start_game_request_in_flight = False

    def _arm_start_watchdog(self, request_token):
        """Set watchdog timer for stuck game start requests."""
        self._cancel_start_watchdog()
        self._start_game_watchdog_event = Clock.schedule_once(
            lambda *_: self._force_unblock_if_stuck(request_token),
            8.0,
        )

    def _cancel_start_watchdog(self):
        """Cancel watchdog timer."""
        if self._start_game_watchdog_event is not None:
            self._start_game_watchdog_event.cancel()
            self._start_game_watchdog_event = None

    def _force_unblock_if_stuck(self, request_token):
        """Force unblock if start request appears stuck."""
        self._start_game_watchdog_event = None
        if request_token != self._start_game_request_token:
            return
        if not self._start_game_request_in_flight:
            return
        self._start_game_request_in_flight = False
        self.screen._start_game_request_in_flight = False
        self.screen.loading_overlay.hide()
        self.screen.start_game_btn.disabled = not self.can_start_game()
        self.screen.status_label.color = self.screen.COLORS["warning"]
        self.screen.status_label.text = "Сервер отвечает слишком долго. Попробуй нажать «Начать игру» ещё раз."

    def reset_for_new_room(self):
        """Reset controller state when entering new room."""
        self._start_game_request_token = 0
        self._start_game_request_in_flight = False
        self._last_start_attempt_ts = 0.0
        self._start_game_watchdog_event = None
        self._local_starts_count = 0
