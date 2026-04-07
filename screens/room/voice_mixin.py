"""Voice and mic mixin for RoomScreen - voice engine, mic toggle, timers."""

import time

from kivy.clock import Clock
from threading import Thread

from services import ping_room_voice, set_room_mic_state
from ui import COLORS


class RoomVoiceMixin:
    """Voice engine lifecycle, mic toggle, countdown/round timers, voice UI sync."""

    # ------------------------------------------------------------------ timers

    def _start_countdown_timer(self, server_time, countdown_left):
        """Start a local countdown timer that updates the overlay every second."""
        self._stop_countdown_timer()
        if countdown_left <= 0:
            return

        try:
            countdown_sec = int(countdown_left) if countdown_left else 0
        except (TypeError, ValueError):
            print(f"[COUNTDOWN_TIMER] Invalid countdown_left: {countdown_left}")
            return

        self._countdown_start_local_time = time.time()
        self._countdown_end_time = self._countdown_start_local_time + countdown_sec
        print(f"[COUNTDOWN_TIMER] Started. Duration: {countdown_sec}s, will end at {self._countdown_end_time:.1f}")
        self._countdown_event = Clock.schedule_interval(self._update_countdown_display, 0.1)

    def _stop_countdown_timer(self):
        """Stop the countdown timer."""
        if self._countdown_event is not None:
            self._countdown_event.cancel()
            self._countdown_event = None
            self._countdown_end_time = 0.0
            self._countdown_start_local_time = 0.0

    def _update_countdown_display(self, _dt):
        """Update countdown overlay display based on elapsed local time."""
        current_local_time = time.time()
        remaining = max(0, self._countdown_end_time - current_local_time)

        if remaining <= 0:
            self._stop_countdown_timer()
            self.countdown_overlay.hide()
            return False

        seconds = max(1, int(remaining))
        self.countdown_overlay._label.text = str(seconds)
        return True

    def _start_round_timer(self, server_time, round_left):
        """Start a local round timer that updates the phase label every second."""
        self._stop_round_timer()
        if round_left <= 0:
            return

        try:
            round_sec = int(round_left) if round_left else 0
        except (TypeError, ValueError):
            print(f"[ROUND_TIMER] Invalid round_left: {round_left}")
            return

        self._round_start_local_time = time.time()
        self._round_end_time = self._round_start_local_time + round_sec
        print(f"[ROUND_TIMER] Started. Duration: {round_sec}s, will end at {self._round_end_time:.1f}")
        self._round_timer_event = Clock.schedule_interval(self._update_round_display, 0.1)

    def _stop_round_timer(self):
        """Stop the round timer."""
        if self._round_timer_event is not None:
            self._round_timer_event.cancel()
            self._round_timer_event = None
            self._round_end_time = 0.0
            self._round_start_local_time = 0.0

    def _update_round_display(self, _dt):
        """Update round timer display based on elapsed local time."""
        current_local_time = time.time()
        remaining = max(0, self._round_end_time - current_local_time)

        if remaining <= 0:
            self._stop_round_timer()
            return False

        seconds = max(1, int(remaining))
        self.phase_label.text = f"ОСТАЛОСЬ {seconds} СЕК"
        return True

    # ------------------------------------------------------------ voice engine

    def _start_voice_ui_sync(self):
        self._stop_voice_ui_sync()
        self._voice_ui_event = Clock.schedule_interval(lambda _dt: self._sync_voice_ui(), 0.08)

    def _stop_voice_ui_sync(self):
        if self._voice_ui_event is not None:
            self._voice_ui_event.cancel()
            self._voice_ui_event = None

    def _start_voice_engine(self):
        player_name = self._player_name()
        if not self.voice_engine.available or not player_name or not self.room_code:
            return

        self.voice_engine.start(
            room_code=self.room_code,
            player_name=player_name,
            should_transmit=lambda: self._can_use_voice() and not self._mic_is_muted(),
        )
        self.voice_engine.set_muted(self._mic_is_muted())

    def _stop_voice_engine(self):
        self.voice_engine.stop()
        self._smoothed_voice_level = 0.0

    # --------------------------------------------------------------- mic state

    def _set_mic_muted(self, muted):
        self._mic_muted_state = bool(muted)
        self.mic_button.set_muted(self._mic_muted_state)
        self.mic_button_top.set_muted(self._mic_muted_state)
        self.voice_engine.set_muted(self._mic_muted_state)

    def _mic_is_muted(self):
        return bool(self._mic_muted_state)

    def _set_mic_enabled(self, enabled):
        self.mic_button.set_enabled(enabled)
        self.mic_button_top.set_enabled(enabled)

    def _set_mic_level(self, level):
        self.mic_button.set_level(level)
        self.mic_button_top.set_level(level)

    # --------------------------------------------------------------- mic toggle

    def _toggle_mic(self, *_):
        print(f"[TOGGLE_MIC] Clicked")
        if not self._can_toggle_mic():
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Микрофон доступен только тому, кто объясняет слова."
            print(f"[TOGGLE_MIC] BLOCKED - not explainer or wrong phase")
            return

        player_name = self._player_name()
        if not player_name or not self.room_code:
            self.status_label.color = COLORS["error"]
            self.status_label.text = "Не удалось определить игрока или комнату."
            print(f"[TOGGLE_MIC] BLOCKED - no player or room")
            return

        old_muted = self._mic_is_muted()
        new_muted = not old_muted
        print(f"[TOGGLE_MIC] Toggling: {old_muted} -> {new_muted}")
        self._set_mic_muted(new_muted)

        Thread(
            target=self._toggle_mic_worker,
            args=(self.room_code, player_name, self._client_id(), old_muted, new_muted),
            daemon=True,
        ).start()

    def _toggle_mic_worker(self, room_code, player_name, client_id, old_muted, new_muted):
        try:
            response = set_room_mic_state(
                room_code=room_code,
                player_name=player_name,
                muted=new_muted,
                client_id=client_id,
            )
            Clock.schedule_once(
                lambda _dt, data=response: self._finish_toggle_mic(data, old_muted, new_muted),
                0,
            )
        except (ConnectionError, ValueError) as error:
            Clock.schedule_once(
                lambda _dt, err=str(error), old=old_muted: self._on_toggle_mic_error(err, old),
                0,
            )

    def _finish_toggle_mic(self, response, old_muted, new_muted):
        updated_state = dict(self.room_state or {})
        if isinstance(response, dict):
            for key in ("room", "voice_active", "voice_speaker", "explainer_mic_state", "server_time"):
                if key in response:
                    updated_state[key] = response.get(key)

            room_payload = response.get("room")
            if isinstance(room_payload, dict) and "explainer_mic_muted" in room_payload:
                updated_state["explainer_mic_muted"] = bool(room_payload.get("explainer_mic_muted"))
                new_version = (room_payload.get("updated_at") or "")
                if new_version > self._room_state_version:
                    self._room_state_version = new_version
            elif "muted" in response:
                updated_state["explainer_mic_muted"] = bool(response.get("muted"))

        self.room_state = updated_state
        final_muted = bool(updated_state.get("explainer_mic_muted", new_muted))
        self._set_mic_muted(final_muted)

        if self._mic_is_muted():
            self.voice_status.text = "Микрофон выключен"
            self.status_label.color = COLORS["text_muted"]
            self.status_label.text = "Микрофон выключен."
        else:
            self.voice_status.text = "Микрофон включен"
            if self.voice_engine.available:
                self.status_label.color = COLORS["success"]
                self.status_label.text = "Микрофон включен."
            else:
                self.status_label.color = COLORS["warning"]
                self.status_label.text = "Микрофон включен, но запись недоступна на этом устройстве."

        self._apply_state()

    def _on_toggle_mic_error(self, error_msg, old_muted):
        self._set_mic_muted(old_muted)
        self.status_label.color = COLORS["error"]
        self.status_label.text = str(error_msg)

    # --------------------------------------------------------------- voice UI sync

    def _sync_voice_ui(self):
        if not self._can_use_voice():
            self._smoothed_voice_level = 0.0
            self._set_mic_level(0.0)
            return
        if not self.voice_engine.available:
            self._smoothed_voice_level = 0.0
            self._set_mic_level(0.0)
            return

        raw_level = self.voice_engine.level() if self.voice_engine.active() else 0.0
        raw_level = max(0.0, min(1.0, raw_level * 6.2))
        if self._mic_is_muted():
            raw_level = 0.0

        smoothing = 0.64 if raw_level >= self._smoothed_voice_level else 0.36
        self._smoothed_voice_level += (raw_level - self._smoothed_voice_level) * smoothing
        if self._smoothed_voice_level < 0.01:
            self._smoothed_voice_level = 0.0

        self._set_mic_level(self._smoothed_voice_level)

        if not self._can_use_voice() or self._mic_is_muted():
            return

        if raw_level < 0.005:
            return

        now_ts = time.time()
        if now_ts - self._last_voice_ping_ts < 0.2:
            return

        self._last_voice_ping_ts = now_ts
        player_name = self._player_name()
        if not player_name:
            return

        try:
            ping_room_voice(
                room_code=self.room_code,
                player_name=player_name,
                active_seconds=3,
                client_id=self._client_id(),
            )
        except (ConnectionError, ValueError):
            pass
