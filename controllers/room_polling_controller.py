"""Room state polling and synchronization."""

import time
from threading import Thread
from kivy.app import App
from kivy.clock import Clock
from services import join_online_room, get_online_room_state


class RoomPollingController:
    """Manages room state synchronization via polling and rejoin."""

    def __init__(self, screen):
        self.screen = screen
        self._poll_event = None
        self._poll_in_flight = False
        self._poll_token = 0
        self._poll_started_at = 0.0
        self._rejoin_request_token = 0
        self._rejoin_in_flight = False
        self._rejoin_recover_attempts = 0

    def start_polling(self):
        """Start periodic room state polling."""
        self.stop_polling()
        self._poll_event = Clock.schedule_interval(lambda _dt: self._poll_state(), 0.65)

    def stop_polling(self):
        """Stop room state polling."""
        if self._poll_event is not None:
            self._poll_event.cancel()
            self._poll_event = None

    def request_rejoin_state(self):
        """Request fresh room state via rejoin."""
        if self._rejoin_in_flight:
            return

        player_name = (self.screen._player_name() or "").strip()
        room_code = (self.screen.room_code or "").strip().upper()
        if not player_name or not room_code:
            return

        app = App.get_running_app()
        self._rejoin_request_token += 1
        request_token = self._rejoin_request_token
        self._rejoin_in_flight = True
        is_guest = bool(app is not None and getattr(app, "guest_mode", False))
        client_id = app.resolve_client_id() if app is not None and hasattr(app, "resolve_client_id") else ""

        Thread(
            target=self._rejoin_worker,
            args=(request_token, room_code, player_name, is_guest, client_id),
            daemon=True,
        ).start()

    def _rejoin_worker(self, request_token, room_code, player_name, is_guest, client_id):
        """Background worker for rejoin request."""
        payload = {
            "token": request_token,
            "status": "error",
            "message": "Не удалось синхронизировать комнату.",
        }
        try:
            joined_room = join_online_room(
                room_code=room_code,
                player_name=player_name,
                is_guest=bool(is_guest),
                client_id=(client_id or "").strip(),
            )
            payload = {
                "token": request_token,
                "status": "success",
                "joined_room": joined_room,
            }
        except ConnectionError as error:
            payload = {"token": request_token, "status": "connection_error", "message": str(error)}
        except ValueError as error:
            payload = {"token": request_token, "status": "value_error", "message": str(error)}

        Clock.schedule_once(lambda _dt, data=payload: self._finish_rejoin_state(data), 0)

    def _finish_rejoin_state(self, payload):
        """Handle rejoin response."""
        token = int(payload.get("token") or 0)
        if token != self._rejoin_request_token:
            return

        self._rejoin_in_flight = False
        if self.screen.manager is None or self.screen.manager.current != self.screen.name:
            return

        status = payload.get("status")
        if status != "success":
            message = payload.get("message") or "Не удалось синхронизировать комнату."
            self.screen.status_label.color = self.screen.COLORS["warning"] if status == "value_error" else self.screen.COLORS["error"]
            self.screen.status_label.text = message
            self.screen._ensure_interaction_ready()
            return

        joined_room = payload.get("joined_room") or {}
        app = App.get_running_app()
        if app is not None:
            joined_as = (joined_room.get("_joined_as") or "").strip()
            if joined_as and hasattr(app, "adopt_room_player_name"):
                app.adopt_room_player_name(joined_as)

        server_state = joined_room.get("_server_state")
        if isinstance(server_state, dict):
            initial_state = dict(server_state)
            incoming_messages = initial_state.get("messages") if isinstance(initial_state.get("messages"), list) else []
            initial_state["messages"] = self.screen._merge_message_history(incoming_messages, since_id=0)
            # Set version FIRST to prevent polling race conditions
            room_data = initial_state.get("room", {})
            if isinstance(room_data, dict):
                self.screen._room_state_version = (room_data.get("updated_at") or "")
            self.screen.room_state = initial_state
            self._rejoin_recover_attempts = 0
            if app is not None:
                app.set_active_room(initial_state.get("room", joined_room))
            self.screen._apply_state()
        elif app is not None:
            app.set_active_room(joined_room)

        self.screen._ensure_interaction_ready()

    def _poll_state(self):
        """Poll for room state updates."""
        if self._poll_in_flight:
            if self._poll_started_at > 0 and (time.time() - self._poll_started_at) > 9.0:
                self._poll_in_flight = False
                self._poll_started_at = 0.0
            else:
                return

        room_code = (self.screen.room_code or "").strip().upper()
        if not room_code:
            self.screen.status_label.color = self.screen.COLORS["warning"]
            self.screen.status_label.text = "Комната не выбрана. Создай комнату или зайди в существующую."
            self.screen._ensure_interaction_ready()
            return

        player_name = (self.screen._player_name() or "").strip()
        if not player_name:
            self.screen.status_label.color = self.screen.COLORS["error"]
            self.screen.status_label.text = "Сессия игрока не найдена. Войди в аккаунт снова."
            self.screen._ensure_interaction_ready()
            return

        self._poll_in_flight = True
        self._poll_started_at = time.time()
        self._poll_token += 1
        request_token = self._poll_token
        since_id = int(self.screen._last_message_id or 0)
        client_id = self.screen._client_id()

        Thread(
            target=self._poll_state_worker,
            args=(request_token, room_code, player_name, client_id, since_id),
            daemon=True,
        ).start()

    def _poll_state_worker(self, request_token, room_code, player_name, client_id, since_id):
        """Background worker for state poll."""
        result = {
            "token": request_token,
            "room_code": room_code,
            "player_name": player_name,
            "client_id": (client_id or "").strip(),
            "since_id": int(since_id or 0),
            "status": "error",
            "message": "Unexpected polling error.",
        }
        try:
            request_since_id = int(since_id or 0)
            state = get_online_room_state(
                room_code=room_code,
                player_name=player_name,
                since_id=request_since_id if request_since_id > 0 else None,
                client_id=(client_id or "").strip(),
                timeout=4,
            )
            result = {
                "token": request_token,
                "room_code": room_code,
                "player_name": player_name,
                "since_id": request_since_id,
                "status": "success",
                "state": state,
            }
        except ConnectionError as error:
            result["status"] = "connection_error"
            result["message"] = str(error)
        except ValueError as error:
            result["status"] = "value_error"
            result["message"] = str(error)
        except Exception as error:
            result["status"] = "error"
            result["message"] = str(error)

        Clock.schedule_once(lambda _dt, payload=result: self._finish_poll_state(payload), 0)

    def _finish_poll_state(self, payload):
        """Handle poll response."""
        token = int(payload.get("token") or 0)
        if token != self._poll_token:
            return

        self._poll_in_flight = False
        self._poll_started_at = 0.0
        if self.screen.manager is None or self.screen.manager.current != self.screen.name:
            return

        print(f"[POLLING_START] _finish_poll_state called")

        if (payload.get("room_code") or "").strip().upper() != (self.screen.room_code or "").strip().upper():
            print(f"[POLLING_START] Room code mismatch, returning")
            return

        status = payload.get("status")
        if status == "success":
            state = dict(payload.get("state") or {})
            incoming_phase = state.get("game_phase", "?")
            incoming_room = state.get("room", {})
            incoming_version = (incoming_room.get("updated_at") or "")
            print(f"[POLLING] Response received. Phase: {incoming_phase}, Version: {incoming_version}, Current version: {self.screen._room_state_version}")

            incoming_messages = state.get("messages") if isinstance(state.get("messages"), list) else []
            used_since = int(payload.get("since_id") or 0)
            state["messages"] = self.screen._merge_message_history(incoming_messages, used_since)
            viewer_state = state.get("viewer") if isinstance(state.get("viewer"), dict) else {}

            if not viewer_state or "is_player" not in viewer_state:
                self.screen.status_label.color = self.screen.COLORS["warning"]
                self.screen.status_label.text = "Сервер не прислал состояние игрока. Повтори вход в комнату."
                self.screen._ensure_interaction_ready()
                return

            if not bool(viewer_state.get("is_player")):
                if self._rejoin_recover_attempts < 2:
                    self._rejoin_recover_attempts += 1
                    self.screen.status_label.color = self.screen.COLORS["warning"]
                    self.screen.status_label.text = "Синхронизируем состав комнаты. Пожалуйста, подожди..."
                    self.request_rejoin_state()
                    self.screen._ensure_interaction_ready()
                    return

                app = App.get_running_app()
                if app is not None:
                    app.clear_active_room()
                    if hasattr(app, "ensure_screen"):
                        app.ensure_screen("join_room")
                self.screen.room_code = ""
                self.screen.room_state = {}
                self.screen._room_state_version = ""
                self.screen.status_label.color = self.screen.COLORS["warning"]
                self.screen.status_label.text = "Ты больше не состоишь в этой комнате."
                Clock.schedule_once(lambda *_: setattr(self.screen.manager, "current", "join_room"), 0)
                self.screen._ensure_interaction_ready()
                return

            # Only apply state if it's newer than what we have (prevents old polling state from overwriting)
            incoming_room = state.get("room", {})
            incoming_version = (incoming_room.get("updated_at") or "")

            # Phase priority to prevent older phases from overwriting newer ones with same timestamp
            phase_priority = {"lobby": 0, "countdown": 1, "round": 2}
            incoming_phase = (state.get("game_phase") or "").strip().lower()
            current_phase = self.screen._current_phase()
            incoming_phase_priority = phase_priority.get(incoming_phase, -1)
            current_phase_priority = phase_priority.get(current_phase, -1)

            state_updated = False
            # Apply if version is newer OR (same version AND incoming phase has higher priority)
            will_apply = incoming_version > self.screen._room_state_version or (
                incoming_version == self.screen._room_state_version and incoming_phase_priority > current_phase_priority
            )
            print(f"[POLLING] Version comparison: '{incoming_version}' > '{self.screen._room_state_version}'? {incoming_version > self.screen._room_state_version}, Phase priority: {incoming_phase}({incoming_phase_priority}) vs {current_phase}({current_phase_priority}), will_apply={will_apply}")

            if will_apply:
                print(f"[POLLING] APPLYING state. Phase changing from {self.screen._current_phase()} to {state.get('game_phase', '?')}")
                # Set version FIRST to prevent race conditions with concurrent requests
                self.screen._room_state_version = incoming_version
                self.screen.room_state = state
                state_updated = True
                # Verify state consistency
                room_version_check = (state.get("room", {}).get("updated_at") or "")
                if room_version_check != incoming_version:
                    print(f"[POLLING] WARNING: State version mismatch! incoming={incoming_version}, room.updated_at={room_version_check}")

                self._rejoin_recover_attempts = 0
                app = App.get_running_app()
                if app is not None:
                    viewer_name = ((state.get("viewer") or {}).get("player_name") or "").strip()
                    if viewer_name and hasattr(app, "adopt_room_player_name"):
                        app.adopt_room_player_name(viewer_name)
                    app.set_active_room(state.get("room", {}))

                # Re-render with the new state
                self.screen._apply_state()
            else:
                current_phase = self.screen._current_phase()
                print(f"[POLLING] SKIPPED - version too old. Current phase stays: {current_phase}")
        elif status == "connection_error":
            self.screen.status_label.color = self.screen.COLORS["error"]
            self.screen.status_label.text = payload.get("message") or "Не удалось обновить комнату."
        elif status == "value_error":
            message = payload.get("message") or "Ошибка обновления комнаты."
            if "Player is not in this room." in message:
                if self._rejoin_recover_attempts < 2:
                    self._rejoin_recover_attempts += 1
                    self.screen.status_label.color = self.screen.COLORS["warning"]
                    self.screen.status_label.text = "Потеряли связь с комнатой. Пробуем переподключиться..."
                    self.request_rejoin_state()
                    self.screen._ensure_interaction_ready()
                    return

                app = App.get_running_app()
                if app is not None:
                    app.clear_active_room()
                    if hasattr(app, "ensure_screen"):
                        app.ensure_screen("join_room")
                self.screen.room_code = ""
                self.screen.room_state = {}
                self.screen.status_label.color = self.screen.COLORS["warning"]
                self.screen.status_label.text = "Ты больше не в этой комнате. Зайди в нее снова."
                Clock.schedule_once(lambda *_: setattr(self.screen.manager, "current", "join_room"), 0)
            else:
                self.screen.status_label.color = self.screen.COLORS["warning"]
                self.screen.status_label.text = message
        else:
            self.screen.status_label.color = self.screen.COLORS["error"]
            self.screen.status_label.text = payload.get("message") or "Не удалось обновить состояние комнаты."

        self.screen._ensure_interaction_ready()

    def reset_for_new_room(self):
        """Reset controller state when entering new room."""
        self.stop_polling()
        self._poll_in_flight = False
        self._poll_token = 0
        self._poll_started_at = 0.0
        self._rejoin_request_token = 0
        self._rejoin_in_flight = False
        self._rejoin_recover_attempts = 0
