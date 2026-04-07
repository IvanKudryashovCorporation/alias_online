"""Layout, rendering, and navigation mixin for RoomScreen."""

import logging
import traceback
from threading import Thread

from kivy.app import App
from kivy.clock import Clock

logger = logging.getLogger(__name__)
from kivy.metrics import dp, sp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup

from services import leave_online_room, sync_room_progress
from ui import (
    AppButton,
    BodyLabel,
    COLORS,
    PixelLabel,
    RoundedPanel,
)


class RoomLayoutMixin:
    """UI layout helpers, apply_state, rendering, navigation, leave popup."""

    # ------------------------------------------------------- transient layers

    def _reset_transient_layers(self):
        self.loading_overlay.hide()
        self.countdown_overlay.hide()
        self._last_chat_mount_signature = None
        self._last_overlay_geometry_signature = None
        self.chat_overlay_layer.clear_widgets()
        self.chat_overlay_layer.size_hint = (None, None)
        self.chat_overlay_layer.size = (0, 0)
        self.chat_overlay_layer.opacity = 0
        self.chat_overlay_layer.disabled = True
        self.score_chat_layer.clear_widgets()
        self.score_chat_layer.opacity = 0
        self.score_chat_layer.disabled = True
        self.chat_host.size_hint_y = 1
        self.chat_host.height = dp(0)
        self.chat_host.opacity = 1
        self.chat_host.disabled = False
        self.lobby_action_bar.opacity = 0
        self.lobby_action_bar.height = dp(0)
        self.lobby_action_bar.disabled = False
        self.chat_card.size_hint = (1, 1)
        self.chat_card.height = dp(0)
        self.chat_card.pos_hint = {}
        self.chat_card.pos = (0, 0)
        self._move_chat_card(self.chat_host)
        self.word_push_spacer.size_hint_y = None
        self.word_push_spacer.height = dp(0)

    # ------------------------------------------------------- start watchdog

    def _cancel_start_watchdog(self):
        if self._start_game_watchdog_event is not None:
            self._start_game_watchdog_event.cancel()
            self._start_game_watchdog_event = None

    def _arm_start_watchdog(self, request_token):
        self._cancel_start_watchdog()
        self._start_game_watchdog_event = Clock.schedule_once(
            lambda *_: self._force_unblock_if_stuck(request_token),
            8.0,
        )

    def _force_unblock_if_stuck(self, request_token):
        self._start_game_watchdog_event = None
        if request_token != self._start_game_request_token:
            return
        if not self._start_game_request_in_flight:
            return
        self._start_game_request_in_flight = False
        self.loading_overlay.hide()
        self.start_game_btn.disabled = not self._can_start_game()
        self.status_label.color = COLORS["warning"]
        self.status_label.text = "Сервер отвечает слишком долго. Попробуй нажать «Начать игру» ещё раз."

    # ------------------------------------------------------- interaction ready

    def _ensure_interaction_ready(self):
        if self.disabled:
            self.disabled = False
        if not self._start_game_request_in_flight:
            self.loading_overlay.hide()
        if self._current_phase() != "round":
            # countdown_overlay visibility is controlled by _apply_state, not here
            self.chat_overlay_layer.clear_widgets()
            self.chat_overlay_layer.size_hint = (None, None)
            self.chat_overlay_layer.size = (0, 0)
            self.chat_overlay_layer.opacity = 0
            self.chat_overlay_layer.disabled = True
            self.score_chat_layer.clear_widgets()
            self.score_chat_layer.opacity = 0
            self.score_chat_layer.disabled = True
            if self.chat_card.parent is self.chat_overlay_layer:
                self._mount_chat_in_column()
        self.back_btn.disabled = False

    # ------------------------------------------------------- navigation

    def _go_back_to_menu(self, *_):
        if self._is_match_active():
            self._open_leave_popup()
            return
        if self.manager is not None:
            self.manager.current = "start"
        Clock.schedule_once(lambda *_: self._leave_room(), 0)

    def _open_player_profile(self, player_name):
        clean_name = (player_name or "").strip()
        if not clean_name:
            return

        app = App.get_running_app()
        viewer_profile = app.current_profile() if app is not None and getattr(app, "authenticated", False) else None
        if viewer_profile is None:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Просмотр профилей игроков доступен только из аккаунта."
            return

        target_profile = self._profile_map().get(clean_name.lower())
        if target_profile is None:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "У этого игрока нет зарегистрированного профиля."
            return

        try:
            profile_screen = self.manager.get_screen("player_profile")
        except Exception:
            self.status_label.color = COLORS["error"]
            self.status_label.text = "Экран профиля недоступен."
            return

        profile_screen.open_for_player(
            player_name=target_profile.name,
            player_email=target_profile.email,
            return_screen="room",
        )
        self.manager.current = "player_profile"

    # ------------------------------------------------------- exit button

    def _set_room_exit_button(self, match_active):
        if match_active:
            self.back_btn.text = "Выйти"
            self.back_btn._rest_button_color = COLORS["danger_button"]
            self.back_btn._pressed_button_color = COLORS["danger_button_pressed"]
        else:
            self.back_btn.text = "В меню"
            self.back_btn._rest_button_color = COLORS["button"]
            self.back_btn._pressed_button_color = COLORS["button_pressed"]
        self.back_btn._button_color.rgba = self.back_btn._rest_button_color

    # ------------------------------------------------------- leave popup

    def _open_leave_popup(self):
        self._dismiss_leave_popup()

        body = BoxLayout(
            orientation="vertical",
            spacing=dp(12),
            padding=[dp(16), dp(16), dp(16), dp(16)],
        )
        panel = RoundedPanel(
            orientation="vertical",
            spacing=dp(12),
            padding=[dp(18), dp(18), dp(18), dp(18)],
            size_hint_y=None,
            height=dp(320),
        )
        panel.add_widget(PixelLabel(text="Выйти из матча?", font_size=sp(20), center=True, size_hint_y=None))
        panel.add_widget(
            BodyLabel(
                center=True,
                color=COLORS["text_muted"],
                font_size=sp(12),
                text="Если выйти сейчас, текущий матч для тебя закончится сразу.",
                size_hint_y=None,
            )
        )

        warning_card = RoundedPanel(
            orientation="vertical",
            spacing=dp(6),
            padding=[dp(14), dp(12), dp(14), dp(12)],
            size_hint_y=None,
            height=dp(108),
            bg_color=(0.28, 0.10, 0.10, 0.92),
            shadow_alpha=0.14,
        )
        warning_card._border_color.rgba = COLORS["error"]
        warning_card._border_line.width = 1.6
        warning_card.add_widget(PixelLabel(text="Предупреждение", font_size=sp(14), center=True, size_hint_y=None))
        warning_card.add_widget(
            BodyLabel(
                center=True,
                color=COLORS["warning"],
                font_size=sp(11),
                text="Снимется 50 AC, а вход и создание комнат будут недоступны в течение 5 минут.",
                size_hint_y=None,
            )
        )
        panel.add_widget(warning_card)

        confirm_btn = AppButton(
            text="Подтвердить выход",
            font_size=sp(17),
            button_color=COLORS["danger_button"],
            pressed_color=COLORS["danger_button_pressed"],
        )
        confirm_btn.bind(on_release=self._confirm_match_exit)
        panel.add_widget(confirm_btn)

        cancel_btn = AppButton(text="Остаться в игре", compact=True, font_size=sp(14))
        cancel_btn.height = dp(46)
        cancel_btn.bind(on_release=lambda *_: self._dismiss_leave_popup())
        panel.add_widget(cancel_btn)
        body.add_widget(panel)

        self.leave_confirm_popup = Popup(
            title="",
            separator_height=0,
            auto_dismiss=True,
            background="atlas://data/images/defaulttheme/modalview-background",
            content=body,
            size_hint=(0.84, None),
            height=dp(360),
        )
        self.leave_confirm_popup.bind(on_dismiss=lambda *_: setattr(self, "leave_confirm_popup", None))
        self.leave_confirm_popup.open()

    def _dismiss_leave_popup(self):
        if self.leave_confirm_popup is not None:
            popup = self.leave_confirm_popup
            self.leave_confirm_popup = None
            popup.dismiss()

    def _confirm_match_exit(self, *_):
        self._dismiss_leave_popup()
        app = App.get_running_app()
        if app is not None and hasattr(app, "apply_room_exit_penalty"):
            penalty_result = app.apply_room_exit_penalty(coin_penalty=50, cooldown_minutes=5)
            if isinstance(penalty_result, dict):
                profile = penalty_result.get("profile")
                if profile is not None:
                    self.coin_badge.set_value(getattr(profile, "alias_coins", 0))
        self._leave_room()
        self.manager.current = "start"

    def _leave_room(self):
        if self._leave_sent:
            return

        app = App.get_running_app()
        room_code = self.room_code or ((app.get_active_room() if app is not None else {}) or {}).get("code", "")
        player_name = self._player_name()
        self._leave_sent = True

        if room_code and player_name:
            Thread(
                target=self._leave_room_worker,
                args=(room_code, player_name, self._client_id()),
                daemon=True,
            ).start()

        self.room_code = ""
        self.room_state = {}
        self._last_chat_signature = None
        self._last_players_signature = None
        self._last_chat_mount_signature = None
        self._last_progress_signature = None
        if app is not None:
            app.clear_active_room()

    def _leave_room_worker(self, room_code, player_name, client_id):
        try:
            leave_online_room(
                room_code=room_code,
                player_name=player_name,
                client_id=(client_id or "").strip(),
            )
        except (ConnectionError, ValueError):
            return

    # ------------------------------------------------------- word card helpers

    def _sync_word_label(self, *_):
        self.word_label.text_size = (max(0, self.word_label.width - dp(12)), max(0, self.word_label.height - dp(12)))

    def _sync_word_stage_layout(self, *_):
        card_width = max(dp(220), self.word_stage.width - dp(12))
        self.word_card.size = (card_width, self.word_card_height)
        self._reset_word_card_position()

    def _reset_word_card_position(self):
        self.word_card.pos = (
            self.word_stage.x + (self.word_stage.width - self.word_card.width) / 2,
            self.word_stage.y + dp(6),
        )
        self.word_card.opacity = 1.0

    def _widget_screen_pos(self, widget):
        x = widget.x
        y = widget.y
        parent = widget.parent
        while parent is not None and parent is not self:
            x += parent.x
            y += parent.y
            parent = parent.parent
        return x, y

    def _set_word_text(self, value):
        word_text = ((value or "").strip() or "...")
        length = len(word_text)
        if length <= 6:
            font_size = sp(58)
        elif length <= 10:
            font_size = sp(50)
        elif length <= 14:
            font_size = sp(42)
        else:
            font_size = sp(34)

        self.word_label.font_size = font_size
        self.word_label.text = word_text

    def _handle_word_swipe(self, _direction):
        if self._current_phase() == "round" and self._can_use_voice():
            self._skip_word()

    # ------------------------------------------------------- players grid

    def _sync_players_grid_width(self, *_):
        cols = max(1, int(getattr(self.players_box, "cols", 1) or 1))
        total_spacing = self.players_box.spacing[0] * (cols - 1) if isinstance(self.players_box.spacing, (list, tuple)) else self.players_box.spacing * (cols - 1)
        total_padding = dp(8)
        available_width = max(dp(96), self.players_scroll.width - dp(12))
        min_width = dp(110) if self.players_box.row_default_height >= dp(120) else dp(86)
        column_width = max(min_width, (available_width - total_spacing - total_padding) / cols)
        self.players_box.col_default_width = column_width
        self.players_box.width = column_width * cols + total_spacing + total_padding

    # ------------------------------------------------------- button / panel visibility

    def _set_button_visibility(self, button, visible):
        if not hasattr(button, "_original_size"):
            button._original_size = tuple(button.size)
            button._original_size_hint = tuple(button.size_hint) if isinstance(button.size_hint, (list, tuple)) else button.size_hint

        button.disabled = not visible
        button.opacity = 1 if visible else 0
        if visible:
            original_hint = button._original_size_hint
            if isinstance(original_hint, (list, tuple)):
                button.size_hint = tuple(original_hint)
            else:
                button.size_hint = original_hint
            button.size = tuple(button._original_size)
        else:
            button.size_hint = (None, None)
            button.size = (dp(0), dp(0))

    def _set_lobby_action_bar_visibility(self, visible, shown_height):
        bar = self.lobby_action_bar
        if visible:
            bar.opacity = 1
            bar.disabled = False
            bar.height = shown_height
        else:
            bar.opacity = 0
            bar.disabled = False
            bar.height = dp(0)

    def _set_panel_visibility(self, panel, visible, shown_height):
        panel.disabled = not visible
        panel.opacity = 1 if visible else 0
        panel.height = shown_height if visible else dp(0)

    def _can_wait_for_host_in_lobby(self):
        viewer = self._viewer_state()
        if viewer and "is_player" in viewer:
            return bool(viewer.get("is_player")) and not self._can_control_start()
        return False

    def _show_lobby_action_row(self, phase):
        if phase != "lobby":
            return False
        return self._can_control_start() or self._can_wait_for_host_in_lobby()

    def _show_explainer_controls(self, is_explainer, phase):
        can_start = phase == "lobby" and self._can_start_game()
        waiting_for_host = phase == "lobby" and self._can_wait_for_host_in_lobby() and not can_start
        self._set_button_visibility(self.start_game_btn, can_start)
        self._set_button_visibility(self.wait_host_btn, waiting_for_host)

    # ------------------------------------------------------- chat layout

    def _set_chat_input_visibility(self, visible):
        row_height = dp(48) if visible else dp(0)
        self.chat_input_row.height = row_height
        self.chat_input_row.opacity = 1 if visible else 0
        self.chat_input_row.disabled = not visible
        self.chat_input.disabled = not visible
        self.chat_input.readonly = not visible
        self.chat_input.opacity = 1 if visible else 0
        self.send_btn.disabled = not visible
        self.send_btn.opacity = 1 if visible else 0
        if not visible:
            self.chat_input.focus = False
            self.chat_input.text = ""

    def _move_chat_card(self, target_parent):
        if target_parent is None:
            return
        current_parent = self.chat_card.parent
        if current_parent is target_parent:
            return
        if current_parent is not None:
            current_parent.remove_widget(self.chat_card)
        target_parent.add_widget(self.chat_card)

    def _mount_chat_in_column(self):
        signature = ("column",)
        if self._last_chat_mount_signature == signature and self.chat_card.parent is self.chat_host:
            return
        self._last_chat_mount_signature = signature
        self._last_overlay_geometry_signature = None
        self.chat_overlay_layer.clear_widgets()
        self.chat_overlay_layer.size_hint = (None, None)
        self.chat_overlay_layer.size = (0, 0)
        self.score_chat_layer.clear_widgets()
        self.chat_overlay_layer.opacity = 0
        self.chat_overlay_layer.disabled = True
        self.score_chat_layer.opacity = 0
        self.score_chat_layer.disabled = True
        self.chat_host.size_hint_y = 1
        self.chat_host.height = dp(0)
        self.chat_host.opacity = 1
        self.chat_host.disabled = False
        self.chat_card.size_hint = (1, 1)
        self.chat_card.height = dp(0)
        self.chat_card.pos_hint = {}
        self.chat_card.pos = (0, 0)
        self._move_chat_card(self.chat_host)
        self.word_push_spacer.size_hint_y = None
        self.word_push_spacer.height = dp(0)

    def _mount_chat_overlay(self, can_chat, is_explainer=False):
        signature = ("overlay", bool(can_chat), bool(is_explainer))
        if self._last_chat_mount_signature == signature and self.chat_card.parent is self.chat_overlay_layer:
            self._sync_overlay_chat_geometry(can_chat, is_explainer)
            return
        self._last_chat_mount_signature = signature
        self._last_overlay_geometry_signature = None
        overlay_height = dp(238 if is_explainer else (214 if can_chat else 182))
        self.chat_overlay_layer.size_hint = (1, 1)
        self.chat_host.size_hint_y = None if is_explainer else 1
        self.chat_host.height = dp(0)
        self.chat_host.opacity = 0
        self.chat_host.disabled = True
        self.chat_card.size_hint = (None, None)
        self.chat_card.height = overlay_height
        self.chat_card.pos_hint = {}
        self.score_chat_layer.clear_widgets()
        self.score_chat_layer.opacity = 0
        self.score_chat_layer.disabled = True
        self.chat_overlay_layer.clear_widgets()
        self.chat_overlay_layer.opacity = 1
        self.chat_overlay_layer.disabled = False
        self.chat_card.width = max(dp(280), self.chat_overlay_layer.width - dp(44))
        self._move_chat_card(self.chat_overlay_layer)
        Clock.schedule_once(lambda *_: self._sync_overlay_chat_geometry(can_chat, is_explainer), 0)

    def _sync_overlay_chat_geometry(self, can_chat, is_explainer):
        if self.chat_card.parent is not self.chat_overlay_layer:
            return

        if is_explainer:
            layout_signature = (
                bool(can_chat),
                True,
                round(float(self.word_stage.x), 1),
                round(float(self.word_stage.y), 1),
                round(float(self.word_stage.width), 1),
                round(float(self.word_stage.height), 1),
                round(float(self.scores_wrap.y), 1),
            )
        else:
            layout_signature = (
                bool(can_chat),
                False,
                round(float(self.chat_overlay_layer.x), 1),
                round(float(self.chat_overlay_layer.y), 1),
                round(float(self.chat_overlay_layer.width), 1),
                round(float(self.chat_overlay_layer.height), 1),
            )
        if layout_signature == self._last_overlay_geometry_signature:
            return
        self._last_overlay_geometry_signature = layout_signature

        overlay_height = dp(238 if is_explainer else (214 if can_chat else 182))
        if is_explainer:
            word_x, word_y = self._widget_screen_pos(self.word_stage)
            _score_panel_x, score_panel_y = self._widget_screen_pos(self.scores_wrap)
            word_top = word_y + self.word_stage.height
            score_limit = score_panel_y - dp(14)

            overlay_height = min(dp(232 if can_chat else 198), max(dp(74), score_limit - word_top - dp(12)))
            overlay_width = min(max(dp(300), self.word_stage.width - dp(18)), dp(430))
            left = word_x + max(0, (self.word_stage.width - overlay_width) / 2)
            bottom = max(word_top + dp(8), score_limit - overlay_height)
            self.chat_card.size = (overlay_width, overlay_height)
            self.chat_card.pos = (left, bottom)
            return

        overlay_width = min(max(dp(300), self.chat_overlay_layer.width - dp(44)), dp(430))
        left = self.chat_overlay_layer.x + (self.chat_overlay_layer.width - overlay_width) / 2
        bottom = max(dp(22), self.chat_overlay_layer.y + dp(22))
        self.chat_card.size = (overlay_width, overlay_height)
        self.chat_card.pos = (left, bottom)

    # ------------------------------------------------------- player cards

    def _render_player_cards(self, players, explainer_name, host_name="", profile_map=None, score_map=None, phase="lobby"):
        from screens.room.widgets import ClickableLobbyPlayerCard, ClickableRoundPlayerRow
        profile_map = profile_map or self._profile_map()
        score_map = score_map or {}
        current_player_name = self._player_name()
        signature = (
            phase,
            tuple(players or []),
            (explainer_name or "").strip().lower(),
            (host_name or "").strip().lower(),
            (current_player_name or "").strip().lower(),
            tuple(sorted(((key or "").strip().lower(), int(value or 0)) for key, value in (score_map or {}).items())),
        )
        if signature == self._last_players_signature:
            return
        self._last_players_signature = signature

        self.players_box.clear_widgets()
        is_round = phase == "round"
        self.players_box.cols = 1 if is_round or not players else 3
        self.players_box.row_default_height = dp(44) if is_round else dp(126)
        self._sync_players_grid_width()
        if not players:
            self.players_box.add_widget(
                BodyLabel(
                    center=True,
                    color=COLORS["text_muted"],
                    font_size=sp(11),
                    text="Игроков пока нет.",
                    size_hint_y=None,
                )
            )
            return

        for listed_player in players:
            card = ClickableRoundPlayerRow() if is_round else ClickableLobbyPlayerCard()
            card.width = self.players_box.col_default_width
            profile = profile_map.get((listed_player or "").strip().lower())
            card.set_player(
                listed_player,
                profile,
                is_explainer=self._same_player(listed_player, explainer_name),
                is_self=self._same_player(listed_player, current_player_name),
                is_host=self._same_player(listed_player, host_name),
                room_score=score_map.get((listed_player or "").strip().lower(), 0),
                phase=phase,
            )
            card.bind(on_release=lambda *_args, player=listed_player: self._open_player_profile(player))
            self.players_box.add_widget(card)

    # ------------------------------------------------------- apply state

    def _apply_state(self):
        logger.debug("[_apply_state] ENTRY")
        try:
            room = self.room_state.get("room", {})
            logger.debug("[_apply_state] Got room dict")

            incoming_version = (room.get("updated_at") or "")
            logger.debug(f"[_apply_state] incoming_version={incoming_version}")

            if self._room_state_version and incoming_version:
                is_older = incoming_version < self._room_state_version
                if is_older:
                    print(f"[APPLY_STATE] SKIPPED - old state. incoming={incoming_version} < current={self._room_state_version}")
                    return

            players = self.room_state.get("players", [])
            scores = self.room_state.get("scores", [])
            messages = self.room_state.get("messages", [])
            viewer = self._viewer_state()

            player_name = self._player_name() or ""
            is_explainer = self._is_explainer()
            phase = self._current_phase()

            stack = traceback.extract_stack()
            caller = "unknown"
            for frame in reversed(stack[-8:-1]):
                if "finish_start_game" in frame.name:
                    caller = "finish_start_game"
                    break
                elif "_finish_poll_state" in frame.name:
                    caller = "polling"
                    break
                elif "on_pre_enter" in frame.name:
                    caller = "on_pre_enter"
                    break
                elif "_finish_rejoin_state" in frame.name:
                    caller = "rejoin"
                    break
                elif "_send_chat_message" in frame.name:
                    caller = "_send_chat_message"
                    break
                elif "_skip_word" in frame.name:
                    caller = "_skip_word"
                    break
                elif "_finish_toggle_mic" in frame.name:
                    caller = "_finish_toggle_mic"
                    break
                elif "sync_room_progress" in frame.name:
                    caller = "sync_room_progress"
                    break
                elif "_ensure_interaction_ready" in frame.name:
                    caller = "_ensure_interaction_ready"
                    break

            print(f"[APPLY_STATE] Phase: {phase}, Version: {room.get('updated_at', '?')}, Caller: {caller}")

            if caller == "unknown":
                caller_frame = stack[-2]
                print(f"[APPLY_STATE] UNKNOWN CALLER: {caller_frame.filename}:{caller_frame.lineno} in {caller_frame.name}")

            logger.debug("[_apply_state] Before _set_room_exit_button")
            self._set_room_exit_button(self._is_match_active())
            logger.debug("[_apply_state] After _set_room_exit_button")
            countdown_left = int(self.room_state.get("countdown_left_sec") or 0)
            round_left = int(self.room_state.get("round_left_sec") or 0)
            explainer_name = room.get("current_explainer") or "—"
            server_mic_muted_raw = self.room_state.get("explainer_mic_muted")
            if server_mic_muted_raw is None and isinstance(room, dict):
                server_mic_muted_raw = room.get("explainer_mic_muted")
            server_mic_muted = bool(server_mic_muted_raw) if server_mic_muted_raw is not None else True
            server_mic_state = (
                (self.room_state.get("explainer_mic_state") or viewer.get("explainer_mic_state") or "").strip().lower()
            )

            room_name = room.get("room_name", "Комната")
            code = room.get("code", self.room_code)
            host_name = room.get("host_name") or ""
            players_count = int(room.get("players_count") or len(players) or 0)
            max_players = int(room.get("max_players") or max(players_count, 1))
            players_text = f"{players_count}/{max_players}"
            logger.debug("[_apply_state] Before _profile_map")
            profile_map = self._profile_map()
            logger.debug("[_apply_state] After _profile_map")
            score_map = {
                (score_entry.get("player_name") or "").strip().lower(): int(score_entry.get("score") or 0)
                for score_entry in scores
            }
            explainer_profile = profile_map.get((explainer_name or "").strip().lower())
            try:
                remote_starts_count = int((room or {}).get("starts_count") or 0)
            except (TypeError, ValueError):
                remote_starts_count = 0
            if remote_starts_count > self._local_starts_count:
                self._local_starts_count = remote_starts_count

            logger.debug("[_apply_state] Before setting labels")
            self.room_meta_label.text = f"{room_name} | Код: {code} | Игроков: {players_text}"
            if phase == "round":
                self.players_wrap_title.text = f"Игроки и очки • {players_text}"
            else:
                self.players_wrap_title.text = f"Игроки в комнате • {players_text}"
            self.players_label.text = f"Игроков: {players_text}"
            logger.debug("[_apply_state] After setting labels")
            logger.debug(f"[_apply_state] About to check if phase == round (phase={phase})")

            if phase == "round":
                logger.debug("[_apply_state] In phase==round block, setting players_wrap_title")
                self.players_wrap_title.text = f"Игроки • {players_text}"
                logger.debug("[_apply_state] After players_wrap_title assignment in round")

            logger.debug("[_apply_state] Before _explainer_chat_locked")
            explainer_can_only_voice = is_explainer and phase == "round"
            explainer_chat_locked = self._explainer_chat_locked()
            logger.debug("[_apply_state] After _explainer_chat_locked")
            explainer_round = explainer_can_only_voice

            round_active = phase == "round"
            logger.debug(f"[_apply_state] Before brand_title assignments (round_active={round_active})")
            self.brand_title.height = dp(0) if round_active else self.brand_title_height
            logger.debug("[_apply_state] After brand_title.height assignment")
            self.brand_title.opacity = 0 if round_active else 1
            logger.debug("[_apply_state] After brand_title.opacity assignment")

            logger.debug("[_apply_state] Before chat_card color assignments")
            if phase == "round":
                self.chat_card._bg_color.rgba = (0.05, 0.09, 0.15, 0.24 if is_explainer else 0.30)
                self.chat_card._border_color.rgba = (1, 1, 1, 0.08)
                self.chat_card._shadow_color.rgba = (0, 0, 0, 0.05)
                self.chat_title.color = COLORS["text"]
            else:
                logger.debug("[_apply_state] In else block: setting chat_card colors (lobby phase)")
                self.chat_card._bg_color.rgba = COLORS["surface"]
                logger.debug("[_apply_state] After chat_card._bg_color assignment")
                self.chat_card._border_color.rgba = COLORS["outline"]
                logger.debug("[_apply_state] After chat_card._border_color assignment")
                self.chat_card._shadow_color.rgba = (0, 0, 0, 0.24)
                logger.debug("[_apply_state] After chat_card._shadow_color assignment")
                self.chat_title.color = COLORS["text"]
                logger.debug("[_apply_state] After chat_title.color assignment")

            logger.debug("[_apply_state] Before _can_send_chat")
            can_chat = self._can_send_chat()
            logger.debug("[_apply_state] After _can_send_chat")
            logger.debug("[_apply_state] About to check explainer_can_only_voice")
            if explainer_can_only_voice:
                logger.debug("[_apply_state] In explainer_can_only_voice block")
                self._set_word_text(self.room_state.get("current_word"))
                self.chat_input.hint_text = "Объясняющий не пишет в чат."
                self._set_mic_enabled(self._can_toggle_mic())
            else:
                logger.debug("[_apply_state] In else block (not explainer)")
                logger.debug("[_apply_state] Before _set_word_text('Слово скрыто')")
                self._set_word_text("Слово скрыто")
                logger.debug("[_apply_state] After _set_word_text('Слово скрыто')")
                if explainer_chat_locked:
                    self.chat_input.hint_text = "Объясняющий не пишет в чат."
                else:
                    self.chat_input.hint_text = "Пиши догадку в чат..." if phase == "round" else "Сообщение в чат..."
                self._set_mic_enabled(False)
                self._set_mic_muted(True)
            if phase == "round" and is_explainer and self._mic_is_muted() != server_mic_muted:
                self._set_mic_muted(server_mic_muted)
            self._set_chat_input_visibility(can_chat)
            if phase == "round":
                self._mount_chat_overlay(can_chat, is_explainer=is_explainer)
            else:
                self._mount_chat_in_column()

            voice_active = bool(self.room_state.get("voice_active"))
            voice_speaker = self.room_state.get("voice_speaker")
            if phase != "round":
                mic_state_text = "ожидает старт"
            elif server_mic_state == "speaking" or (voice_active and self._same_player(voice_speaker, explainer_name)):
                mic_state_text = "говорит"
            elif server_mic_state == "off" or server_mic_muted:
                mic_state_text = "выключен"
            elif server_mic_state == "on":
                mic_state_text = "включен"
            else:
                mic_state_text = "молчит"
            self.explainer_card.set_explainer(explainer_name, explainer_profile, mic_state_text)
            if not self.voice_engine.available:
                self.voice_status.text = "Голос недоступен на этом устройстве."
            elif self._mic_is_muted():
                self.voice_status.text = "Выключен"
            elif voice_active and self._same_player(voice_speaker, explainer_name):
                self.voice_status.text = "Говоришь"
            else:
                self.voice_status.text = "Включен"
            if phase == "lobby":
                if self._can_control_start():
                    self.explainer_status_label.text = f"Объясняет слова: {explainer_name} | Ты: хост"
                else:
                    self.explainer_status_label.text = f"Объясняет слова: {explainer_name} | Ты: отгадывающий"
                self.wait_host_btn.text = f"Ожидание: {explainer_name} запускает игру"
            else:
                self.explainer_status_label.text = f"Объясняет слова: {explainer_name} | Микрофон: {mic_state_text}"

            logger.debug("[_apply_state] Before _show_explainer_controls")
            self._show_explainer_controls(is_explainer, phase)
            logger.debug("[_apply_state] Before panel visibility updates")
            show_players_grid = phase in {"lobby", "round"}
            players_panel_height = self.players_wrap_round_height if phase == "round" else self.players_wrap_height
            scores_panel_height = self.scores_wrap_overlay_height if phase == "round" and is_explainer else self.scores_wrap_height
            logger.debug("[_apply_state] Before _set_panel_visibility calls")
            self._set_panel_visibility(self.room_meta_wrap, phase not in {"lobby", "round"} and not is_explainer, self.room_meta_wrap_height)
            self._set_panel_visibility(self.players_wrap, show_players_grid, players_panel_height)
            self._set_panel_visibility(self.players_summary_wrap, False, self.players_summary_wrap_height)
            self._set_lobby_action_bar_visibility(
                self._show_lobby_action_row(phase),
                self.lobby_start_height,
            )
            lobby_bar_visible = phase == "lobby" and self._show_lobby_action_row(phase)
            self._content_box.padding[3] = dp(10) + (self.lobby_start_height if lobby_bar_visible else 0)
            self._set_panel_visibility(self.explainer_card, phase in {"countdown", "round"} and not is_explainer, self.explainer_card_height)
            self._set_panel_visibility(self.word_stage, phase == "round" and is_explainer, self.word_stage_height)
            self._set_panel_visibility(self.voice_card, False, self.voice_card_height)
            self._set_panel_visibility(self.scores_wrap, phase == "round" and is_explainer, scores_panel_height)
            self._set_panel_visibility(self.phase_wrap, phase in {"countdown", "round"}, self.phase_wrap_height)
            self._content_scroll.disabled = False
            self._content_scroll.do_scroll_y = phase == "lobby"
            if phase == "lobby":
                self.chat_host.size_hint_y = None
                self.chat_host.height = dp(210)
            else:
                self.chat_host.size_hint_y = 1
                self.chat_host.height = dp(0)
            if phase == "round" and is_explainer:
                self.word_push_spacer.size_hint_y = 1
                self.word_push_spacer.height = dp(0)
            else:
                self.word_push_spacer.size_hint_y = None
                self.word_push_spacer.height = dp(0)
            self.mic_button_top.opacity = 1 if phase == "round" and is_explainer else 0
            self.mic_button_top.disabled = not (phase == "round" and is_explainer)

            if phase == "lobby":
                self.phase_label.text = ""
                print(f"[PHASE] Hiding countdown overlay (lobby)")
                self._stop_countdown_timer()
                self._stop_round_timer()
                self.countdown_overlay.hide()
            elif phase == "countdown":
                self.phase_label.color = COLORS["accent"]
                self.phase_label.text = f"СТАРТ ЧЕРЕЗ {countdown_left} СЕК"
                print(f"[PHASE] Showing countdown overlay ({countdown_left} sec)")
                if countdown_left > 0:
                    self.countdown_overlay.show(countdown_left)
                else:
                    self.countdown_overlay.show(1)
                if self._countdown_event is None:
                    server_time = self.room_state.get("server_time", 0)
                    if server_time:
                        self._start_countdown_timer(server_time, countdown_left)
            else:
                self.phase_label.color = COLORS["success"]
                self.phase_label.text = f"ОСТАЛОСЬ {round_left} СЕК"
                print(f"[PHASE] Hiding countdown overlay (round)")
                self._stop_countdown_timer()
                self.countdown_overlay.hide()
                if self._round_timer_event is None:
                    server_time = self.room_state.get("server_time", 0)
                    if server_time:
                        self._start_round_timer(server_time, round_left)

            logger.debug("[_apply_state] Before _render_player_cards")
            self._render_player_cards(players, explainer_name, host_name, profile_map, score_map, phase)
            logger.debug("[_apply_state] After _render_player_cards")
            if phase == "round" and is_explainer:
                logger.debug("[_apply_state] Before _sync_word_stage_layout")
                self._sync_word_stage_layout()
                logger.debug("[_apply_state] After _sync_word_stage_layout")

            current_player_score = 0
            for score_entry in scores:
                if score_entry.get("player_name") == player_name:
                    try:
                        current_player_score = int(score_entry.get("score") or 0)
                    except (TypeError, ValueError):
                        current_player_score = 0
                    break
            self.score_badge.set_score(current_player_score)
            self._sync_profile_progress(
                current_player_score,
                phase,
                role="explainer" if is_explainer else "guesser",
            )
            self.coin_badge.refresh_from_session()

            logger.debug("[_apply_state] Rendering messages")
            self._render_messages(messages)
            logger.debug("[_apply_state] Ensuring interaction ready")
            self._ensure_interaction_ready()
            logger.info("[_apply_state] COMPLETED SUCCESSFULLY")
        except Exception as e:
            logger.error("[_apply_state] CRASHED", exc_info=True)
            raise

    # ------------------------------------------------------- profile progress

    def _sync_profile_progress(self, current_score, phase, role):
        app = App.get_running_app()
        if app is None or not getattr(app, "authenticated", False) or not self.room_code:
            return

        profile = app.current_profile()
        if profile is None:
            return

        sync_signature = (
            (profile.email or "").strip().lower(),
            (self.room_code or "").strip().upper(),
            int(current_score or 0),
            (phase or "").strip().lower(),
            (role or "").strip().lower(),
        )
        if sync_signature == self._last_progress_signature:
            return
        self._last_progress_signature = sync_signature

        sync_room_progress(
            email=profile.email,
            room_code=self.room_code,
            current_score=current_score,
            round_started=phase == "round",
            role=role,
        )
