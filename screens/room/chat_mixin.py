"""Chat and word-skip mixin for RoomScreen."""

from threading import Thread
from types import SimpleNamespace

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import sp

from services import (
    ROOM_CREATION_COST,
    send_room_chat,
    send_room_guess,
    skip_room_word,
    spend_alias_coins,
)
from ui import COLORS, BodyLabel


class RoomChatMixin:
    """Message history, chat send, word skip, start-cost charge, message rendering."""

    # ---------------------------------------------------------- message history

    def _normalize_message_rows(self, messages):
        normalized = []
        for message in messages or []:
            if not isinstance(message, dict):
                continue
            try:
                message_id = int(message.get("id"))
            except (TypeError, ValueError):
                continue
            entry = dict(message)
            entry["id"] = message_id
            normalized.append(entry)
        normalized.sort(key=lambda item: int(item.get("id", 0)))
        return normalized

    def _merge_message_history(self, incoming_messages, since_id):
        normalized_incoming = self._normalize_message_rows(incoming_messages)
        if since_id <= 0 or not self._message_history:
            merged = normalized_incoming
        else:
            merged_map = {}
            for item in self._message_history:
                if isinstance(item, dict):
                    try:
                        merged_map[int(item.get("id"))] = item
                    except (TypeError, ValueError):
                        continue
            for item in normalized_incoming:
                merged_map[int(item["id"])] = item
            merged_ids = sorted(merged_map.keys())
            merged = [merged_map[message_id] for message_id in merged_ids]

        if len(merged) > 180:
            merged = merged[-180:]

        self._message_history = list(merged)
        self._last_message_id = int(merged[-1]["id"]) if merged else 0
        return list(merged)

    # ---------------------------------------------------------- render messages

    def _render_messages(self, messages):
        messages = list(messages or [])
        signature = tuple(
            (message.get("id"), message.get("message_type"), message.get("player_name"), message.get("message"))
            for message in messages[-100:]
        )
        if signature == self._last_chat_signature:
            return
        self._last_chat_signature = signature

        phase = self._current_phase()
        is_explainer = self._is_explainer()
        display_messages = list(messages[-22:]) if phase == "round" else list(messages[-30:])
        self.chat_box.clear_widgets()

        if not display_messages:
            self.chat_box.add_widget(
                BodyLabel(
                    center=True,
                    color=COLORS["text_muted"],
                    font_size=sp(11),
                    text="Чат пуст. Напиши первое сообщение.",
                    size_hint_y=None,
                )
            )
            Clock.schedule_once(lambda *_: setattr(self.chat_scroll, "scroll_y", 0), 0)
            return

        for message in display_messages:
            message_type = message.get("message_type", "chat")
            sender = message.get("player_name", "")
            text = message.get("message", "")

            if message_type == "system":
                line = f"[Система] {text}"
                color = COLORS["warning"]
            elif message_type == "guess":
                line = f"{sender}: {text}"
                color = COLORS["text_soft"]
            else:
                line = f"{sender}: {text}"
                color = COLORS["text"]

            self.chat_box.add_widget(
                BodyLabel(
                    text=line,
                    color=color,
                    font_size=sp(10.2 if phase == "round" and is_explainer else 11.6),
                    size_hint_y=None,
                )
            )

        Clock.schedule_once(lambda *_: setattr(self.chat_scroll, "scroll_y", 0), 0)

    # ---------------------------------------------------------- start cost

    def _charge_start_cost(self):
        app = App.get_running_app()
        if app is None:
            return True, None

        if getattr(app, "authenticated", False):
            profile = app.current_profile()
            if profile is None:
                return True, None

            try:
                current_coins = int(getattr(profile, "alias_coins", 0) or 0)
            except (TypeError, ValueError):
                current_coins = 0

            if current_coins < ROOM_CREATION_COST:
                return (
                    False,
                    f"Нужно минимум {ROOM_CREATION_COST} AC для запуска игры. Сейчас: {current_coins} AC.",
                )

            try:
                updated_profile = spend_alias_coins(
                    email=profile.email,
                    amount=ROOM_CREATION_COST,
                    increment_rooms_created=False,
                    reason_label="запуск игры",
                )
            except ValueError as error:
                return False, str(error)

            self.coin_badge.set_value(updated_profile.alias_coins)
            return True, updated_profile

        if getattr(app, "guest_mode", False):
            current_coins = int(app.current_alias_coins() or 0)
            if current_coins < ROOM_CREATION_COST:
                return (
                    False,
                    f"Нужно минимум {ROOM_CREATION_COST} AC для запуска игры. Сейчас: {current_coins} AC.",
                )
            spent_ok, remaining = app.try_spend_guest_alias_coins(ROOM_CREATION_COST)
            if not spent_ok:
                return (
                    False,
                    f"Нужно минимум {ROOM_CREATION_COST} AC для запуска игры. Сейчас: {current_coins} AC.",
                )
            self.coin_badge.set_value(int(remaining))
            return True, SimpleNamespace(alias_coins=int(remaining))

        return True, None

    # ---------------------------------------------------------- send chat

    def _send_chat_message(self, *_):
        if self._chat_request_in_flight:
            return
        if not self._can_send_chat():
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Объясняющий не может писать в чат. Только объяснять голосом."
            return

        text = self.chat_input.text.strip()
        if not text:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Введи текст сообщения."
            return

        player_name = self._player_name()
        if not player_name:
            self.status_label.color = COLORS["error"]
            self.status_label.text = "Сессия игрока не найдена."
            return

        phase = self._current_phase()
        self._chat_request_in_flight = True
        self._chat_request_token += 1
        request_token = self._chat_request_token
        self.send_btn.disabled = True

        Thread(
            target=self._send_chat_worker,
            args=(request_token, phase, self.room_code, player_name, self._client_id(), text),
            daemon=True,
        ).start()

    def _send_chat_worker(self, request_token, phase, room_code, player_name, client_id, text):
        payload = {
            "token": request_token,
            "phase": phase,
            "status": "error",
            "tone": "error",
            "message": "Не удалось отправить сообщение.",
        }
        try:
            if phase == "round":
                result = send_room_guess(
                    room_code=room_code,
                    player_name=player_name,
                    guess=text,
                    client_id=(client_id or "").strip(),
                )
                payload = {
                    "token": request_token,
                    "phase": phase,
                    "status": "success",
                    "result": result,
                }
            else:
                send_room_chat(
                    room_code=room_code,
                    player_name=player_name,
                    message=text,
                    client_id=(client_id or "").strip(),
                )
                payload = {
                    "token": request_token,
                    "phase": phase,
                    "status": "success",
                    "result": None,
                }
        except ConnectionError as error:
            payload["status"] = "error"
            payload["tone"] = "error"
            payload["message"] = str(error)
        except ValueError as error:
            payload["status"] = "error"
            payload["tone"] = "warning"
            payload["message"] = str(error)
        except Exception as error:
            payload["status"] = "error"
            payload["tone"] = "error"
            payload["message"] = str(error)

        Clock.schedule_once(lambda _dt, data=payload: self._finish_send_chat(data), 0)

    def _finish_send_chat(self, payload):
        token = int(payload.get("token") or 0)
        if token != self._chat_request_token:
            return

        self._chat_request_in_flight = False
        self.send_btn.disabled = False

        if payload.get("status") != "success":
            tone = payload.get("tone", "error")
            self.status_label.color = COLORS["warning"] if tone == "warning" else COLORS["error"]
            self.status_label.text = payload.get("message") or "Не удалось отправить сообщение."
            return

        phase = payload.get("phase")
        result = payload.get("result") or {}
        if phase == "round":
            if result.get("correct"):
                awarded_player = result.get("awarded_player") or "объясняющий"
                guesser_player = result.get("guesser_player") or (self._player_name() or "игрок")
                self.status_label.color = COLORS["success"]
                self.status_label.text = f"Верно! {awarded_player} +1 и {guesser_player} +1."
            else:
                self.status_label.color = COLORS["text_muted"]
                self.status_label.text = "Догадка отправлена."
        else:
            self.status_label.color = COLORS["success"]
            self.status_label.text = "Сообщение отправлено."

        if isinstance(result, dict) and result:
            updated_state = dict(self.room_state or {})
            if "room" in result:
                updated_state["room"] = result.get("room") or {}
                room_data = updated_state.get("room", {})
                if isinstance(room_data, dict):
                    new_version = (room_data.get("updated_at") or "")
                    if new_version > self._room_state_version:
                        self._room_state_version = new_version
            if "scores" in result:
                updated_state["scores"] = result.get("scores") or []
            if "current_word" in result:
                updated_state["current_word"] = result.get("current_word") or ""
            self.room_state = updated_state
            self._apply_state()

        self.chat_input.text = ""

    # ---------------------------------------------------------- skip word

    def _skip_word(self, *_):
        if self._skip_request_in_flight:
            return
        if not self._is_explainer():
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Скипать слова может только объясняющий."
            return
        if self._current_phase() != "round":
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Скип доступен только во время раунда."
            return

        player_name = (self._player_name() or "").strip()
        if not player_name:
            self.status_label.color = COLORS["error"]
            self.status_label.text = "Сессия игрока не найдена."
            return

        self._skip_request_in_flight = True
        self._skip_request_token += 1
        request_token = self._skip_request_token
        Thread(
            target=self._skip_word_worker,
            args=(request_token, self.room_code, player_name, self._client_id()),
            daemon=True,
        ).start()

    def _skip_word_worker(self, request_token, room_code, player_name, client_id):
        payload = {
            "token": request_token,
            "status": "error",
            "tone": "error",
            "message": "Не удалось скипнуть слово.",
        }
        try:
            response = skip_room_word(
                room_code=room_code,
                player_name=player_name,
                client_id=(client_id or "").strip(),
            )
            payload = {"token": request_token, "status": "success", "response": response}
        except ConnectionError as error:
            payload["status"] = "error"
            payload["tone"] = "error"
            payload["message"] = str(error)
        except ValueError as error:
            payload["status"] = "error"
            payload["tone"] = "warning"
            payload["message"] = str(error)
        except Exception as error:
            payload["status"] = "error"
            payload["tone"] = "error"
            payload["message"] = str(error)

        Clock.schedule_once(lambda _dt, data=payload: self._finish_skip_word(data), 0)

    def _finish_skip_word(self, payload):
        token = int(payload.get("token") or 0)
        if token != self._skip_request_token:
            return

        self._skip_request_in_flight = False
        if payload.get("status") != "success":
            tone = payload.get("tone", "error")
            self.status_label.color = COLORS["warning"] if tone == "warning" else COLORS["error"]
            self.status_label.text = payload.get("message") or "Не удалось скипнуть слово."
            return

        response = payload.get("response") or {}
        self.status_label.color = COLORS["warning"]
        self.status_label.text = f"Слово скипнуто. Штраф {response.get('delta', -1)}."
        if isinstance(response, dict):
            updated_state = dict(self.room_state or {})
            if "room" in response:
                updated_state["room"] = response.get("room") or {}
                room_data = updated_state.get("room", {})
                if isinstance(room_data, dict):
                    new_version = (room_data.get("updated_at") or "")
                    if new_version > self._room_state_version:
                        self._room_state_version = new_version
            if "scores" in response:
                updated_state["scores"] = response.get("scores") or []
            if "current_word" in response:
                updated_state["current_word"] = response.get("current_word") or ""
            updated_state["game_phase"] = "round"
            self.room_state = updated_state
            self.word_card.opacity = 1.0
            self._apply_state()
