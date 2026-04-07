"""State query mixin for RoomScreen - viewer state, permissions, phase checks."""

import logging
import time

from kivy.app import App

from services import list_profiles

logger = logging.getLogger(__name__)


class RoomStateMixin:
    """Pure state query methods - no side effects, no UI changes."""

    def _player_name(self):
        viewer_name = ((self._viewer_state().get("player_name") or "").strip())
        if viewer_name:
            return viewer_name
        app = App.get_running_app()
        if app is None:
            return None
        if hasattr(app, "resolve_room_player_name"):
            return app.resolve_room_player_name(room_code=self.room_code)
        return app.resolve_player_name() if hasattr(app, "resolve_player_name") else None

    def _client_id(self):
        app = App.get_running_app()
        if app is None or not hasattr(app, "resolve_client_id"):
            return ""
        return (app.resolve_client_id() or "").strip()

    def _normalized_player_name(self, value):
        return (value or "").strip().casefold()

    def _same_player(self, left, right):
        return bool(self._normalized_player_name(left) and self._normalized_player_name(left) == self._normalized_player_name(right))

    def _viewer_state(self):
        viewer = self.room_state.get("viewer", {})
        return viewer if isinstance(viewer, dict) else {}

    def _current_phase(self):
        phase = (self.room_state.get("game_phase") or "").strip().lower()
        if phase in {"lobby", "countdown", "round"}:
            return phase
        room_phase = (self.room_state.get("room", {}).get("game_phase") or "").strip().lower()
        if room_phase in {"lobby", "countdown", "round"}:
            return room_phase
        return "lobby"

    def _is_match_active(self):
        phase = self._current_phase()
        if phase in {"countdown", "round"}:
            return True
        room = self.room_state.get("room", {}) if isinstance(self.room_state, dict) else {}
        room_phase = (room.get("game_phase") or "").strip().lower()
        return room_phase in {"countdown", "round"}

    def _is_explainer(self):
        viewer = self._viewer_state()
        if viewer and "is_explainer" in viewer:
            return bool(viewer.get("is_explainer"))
        return False

    def _is_host(self):
        viewer = self._viewer_state()
        if viewer and "is_host" in viewer:
            return bool(viewer.get("is_host"))
        return False

    def _can_control_start(self):
        viewer = self._viewer_state()
        if viewer and "can_control_start" in viewer:
            return bool(viewer.get("can_control_start"))
        return False

    def _can_start_game(self):
        viewer = self._viewer_state()
        if viewer and "can_start_game" in viewer:
            return bool(viewer.get("can_start_game"))
        return False

    def _explainer_chat_locked(self):
        return self._is_explainer() and self._current_phase() in {"countdown", "round"}

    def _can_send_chat(self):
        logger.debug("[_can_send_chat] ENTRY")
        logger.debug("[_can_send_chat] Checking _explainer_chat_locked")
        if self._explainer_chat_locked():
            logger.debug("[_can_send_chat] Returning False (explainer locked)")
            return False
        logger.debug("[_can_send_chat] Getting viewer state")
        viewer = self._viewer_state()
        logger.debug(f"[_can_send_chat] Viewer state retrieved: {bool(viewer)}")
        if viewer and "can_send_chat" in viewer:
            result = bool(viewer.get("can_send_chat"))
            logger.debug(f"[_can_send_chat] Returning {result} from viewer state")
            return result
        logger.debug("[_can_send_chat] Returning False (default)")
        return False

    def _can_use_voice(self):
        if self._current_phase() != "round":
            return False
        viewer = self._viewer_state()
        if viewer and "can_use_voice" in viewer:
            return bool(viewer.get("can_use_voice"))
        return False

    def _can_toggle_mic(self):
        if self._current_phase() != "round":
            return False
        viewer = self._viewer_state()
        if viewer and "can_toggle_mic" in viewer:
            return bool(viewer.get("can_toggle_mic"))
        return False

    def _required_players_to_start(self, room):
        viewer = self._viewer_state()
        if isinstance(viewer, dict):
            try:
                required = int(viewer.get("required_players_to_start") or 1)
            except (TypeError, ValueError):
                required = 1
            return max(1, required)
        return 1

    def _profile_map(self):
        now_ts = time.time()
        if self._profile_cache and now_ts - self._profile_cache_ts < 2.0:
            return self._profile_cache
        try:
            cache = {profile.name.strip().lower(): profile for profile in list_profiles()}
            self._profile_cache = cache
            self._profile_cache_ts = now_ts
            return cache
        except Exception:
            return self._profile_cache or {}
