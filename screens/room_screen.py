import time

from kivy.app import App
from kivy.clock import Clock
from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from services import (
    RoomVoiceEngine,
    get_online_room_state,
    leave_online_room,
    list_profiles,
    ping_room_voice,
    send_room_chat,
    send_room_guess,
    skip_room_word,
    start_room_game,
    sync_room_progress,
)
from ui import (
    AppButton,
    AppTextInput,
    AvatarButton,
    BodyLabel,
    BrandTitle,
    CoinBadge,
    COLORS,
    PixelLabel,
    RoundedPanel,
    ScreenBackground,
    register_game_font,
)


class VoiceMicButton(ButtonBehavior, Widget):
    def __init__(self, **kwargs):
        super().__init__(size_hint=(None, None), size=(dp(94), dp(94)), **kwargs)
        self._muted = True
        self._enabled = True
        self._level = 0.0

        with self.canvas.before:
            self._shadow_color = Color(0, 0, 0, 0.22)
            self._shadow = Ellipse(pos=self.pos, size=self.size)
            self._bg_color = Color(0.08, 0.13, 0.21, 0.96)
            self._bg = Ellipse(pos=self.pos, size=self.size)

            self._mic_color = Color(0.96, 0.98, 1.0, 1.0)
            self._capsule = RoundedRectangle(radius=[dp(10)] * 4)
            self._stem = RoundedRectangle(radius=[dp(2)] * 4)
            self._base = RoundedRectangle(radius=[dp(2)] * 4)

            self._outline_color = Color(1, 1, 1, 0.2)
            self._outline = Line(width=1.2, ellipse=(self.x, self.y, self.width, self.height))

            self._mute_color = Color(0.96, 0.23, 0.23, 0.0)
            self._mute_line = Line(width=dp(3.2), points=[])

        self.bind(pos=self._sync_canvas, size=self._sync_canvas)

    @property
    def muted(self):
        return self._muted

    def set_muted(self, muted):
        self._muted = bool(muted)
        self._refresh_state()

    def set_enabled(self, enabled):
        self._enabled = bool(enabled)
        self._refresh_state()

    def set_level(self, level):
        self._level = max(0.0, min(1.0, float(level)))
        self._refresh_state()

    def on_press(self):
        if not self._enabled:
            return
        self._bg_color.rgba = (0.06, 0.10, 0.16, 0.96)

    def on_release(self):
        self._refresh_state()

    def _refresh_state(self):
        if not self._enabled:
            self._bg_color.rgba = (0.14, 0.14, 0.16, 0.82)
            self._mic_color.rgba = (0.65, 0.68, 0.72, 1.0)
            self._mute_color.rgba = (0.96, 0.23, 0.23, 0.42)
        else:
            self._bg_color.rgba = (0.08, 0.13, 0.21, 0.96)
            if self._muted:
                self._mic_color.rgba = (0.96, 0.98, 1.0, 1.0)
            else:
                # Fill the mic icon itself with green based on speech level.
                level = self._level
                red = 0.96 * (1 - level) + 0.21 * level
                green = 0.98 * (1 - level) + 0.90 * level
                blue = 1.00 * (1 - level) + 0.36 * level
                self._mic_color.rgba = (red, green, blue, 1.0)
            self._mute_color.rgba = (0.96, 0.23, 0.23, 0.95 if self._muted else 0.0)

        self._sync_canvas()

    def _sync_canvas(self, *_):
        self._shadow.pos = (self.x, self.y - dp(2))
        self._shadow.size = self.size
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._outline.ellipse = (self.x, self.y, self.width, self.height)

        capsule_w = self.width * 0.30
        capsule_h = self.height * 0.40
        self._capsule.pos = (self.center_x - capsule_w / 2, self.y + self.height * 0.52 - capsule_h / 2)
        self._capsule.size = (capsule_w, capsule_h)

        stem_w = self.width * 0.055
        stem_h = self.height * 0.13
        self._stem.pos = (self.center_x - stem_w / 2, self.y + self.height * 0.29)
        self._stem.size = (stem_w, stem_h)

        base_w = self.width * 0.34
        base_h = self.height * 0.05
        self._base.pos = (self.center_x - base_w / 2, self.y + self.height * 0.21)
        self._base.size = (base_w, base_h)

        self._mute_line.points = [
            self.x + self.width * 0.24,
            self.y + self.height * 0.26,
            self.x + self.width * 0.76,
            self.y + self.height * 0.74,
        ]


class SwipeWordCard(RoundedPanel):
    def __init__(self, swipe_callback=None, swipe_threshold=44, **kwargs):
        self._swipe_callback = swipe_callback
        self._swipe_start = None
        self._swipe_threshold = dp(swipe_threshold)
        super().__init__(**kwargs)

    def set_swipe_callback(self, callback):
        self._swipe_callback = callback

    def on_touch_down(self, touch):
        if getattr(self, "disabled", False) or not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        self._swipe_start = touch.pos
        touch.grab(self)
        return True

    def on_touch_up(self, touch):
        if touch.grab_current is not self:
            return super().on_touch_up(touch)

        touch.ungrab(self)
        start_pos = self._swipe_start
        self._swipe_start = None
        if not start_pos:
            return True

        delta_x = touch.x - start_pos[0]
        delta_y = touch.y - start_pos[1]
        if abs(delta_y) >= self._swipe_threshold and abs(delta_y) > abs(delta_x):
            if self._swipe_callback is not None:
                self._swipe_callback("up" if delta_y > 0 else "down")
        return True


class ScoreCircleWidget(FloatLayout):
    def __init__(self, **kwargs):
        super().__init__(size_hint=(None, None), size=(dp(132), dp(132)), **kwargs)
        with self.canvas.before:
            self._shadow_color = Color(0, 0, 0, 0.24)
            self._shadow = Ellipse(pos=(self.x, self.y - dp(2)), size=self.size)
            self._bg_color = Color(0.08, 0.13, 0.21, 0.96)
            self._bg = Ellipse(pos=self.pos, size=self.size)
            self._ring_color = Color(*COLORS["accent"])
            self._ring = Line(width=dp(2), ellipse=(self.x, self.y, self.width, self.height))

        self._score_label = Label(
            text="0",
            font_name="BrandFont",
            font_size=sp(56),
            color=COLORS["accent"],
            halign="center",
            valign="middle",
        )
        self.add_widget(self._score_label)
        self.bind(pos=self._sync_canvas, size=self._sync_canvas)

    def set_score(self, value):
        try:
            score = int(value)
        except (TypeError, ValueError):
            score = 0
        self._score_label.text = str(score)

    def _sync_canvas(self, *_):
        self._shadow.pos = (self.x, self.y - dp(2))
        self._shadow.size = self.size
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._ring.ellipse = (self.x, self.y, self.width, self.height)
        self._score_label.pos = self.pos
        self._score_label.size = self.size
        self._score_label.text_size = self.size


class ScoreBadge(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(
            orientation="vertical",
            spacing=dp(4),
            size_hint=(None, None),
            size=(dp(180), dp(170)),
            **kwargs,
        )
        self.caption = PixelLabel(text="СЧЕТ:", center=True, font_size=sp(17), size_hint_y=None)
        self.add_widget(self.caption)

        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(136))
        row.add_widget(Widget())
        self.circle = ScoreCircleWidget()
        row.add_widget(self.circle)
        row.add_widget(Widget())
        self.add_widget(row)

    def set_score(self, value):
        self.circle.set_score(value)


class LobbyPlayerCard(RoundedPanel):
    def __init__(self, **kwargs):
        super().__init__(
            orientation="vertical",
            spacing=dp(2),
            padding=[dp(5), dp(5), dp(5), dp(5)],
            size_hint_x=None,
            size_hint_y=None,
            height=dp(78),
            bg_color=COLORS["surface_panel"],
            shadow_alpha=0.14,
            **kwargs,
        )
        avatar_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(28))
        avatar_row.add_widget(Widget())
        self.avatar = AvatarButton()
        self.avatar.size = (dp(26), dp(26))
        self.avatar.disabled = True
        avatar_row.add_widget(self.avatar)
        avatar_row.add_widget(Widget())
        self.add_widget(avatar_row)

        text_col = BoxLayout(orientation="vertical", spacing=dp(0), size_hint_y=None, height=dp(28))
        self.games_label = BodyLabel(text="", center=True, color=COLORS["text_soft"], font_size=sp(8.5), size_hint_y=None)
        text_col.add_widget(self.games_label)
        self.earned_label = BodyLabel(text="", center=True, color=COLORS["accent"], font_size=sp(8.5), size_hint_y=None)
        text_col.add_widget(self.earned_label)
        self.add_widget(text_col)

    def set_player(self, player_name, profile, is_explainer=False):
        self.avatar.set_profile(profile)
        games_played = getattr(profile, "games_played", 0) if profile is not None else 0
        total_earned = getattr(profile, "total_points", 0) if profile is not None else 0
        self.games_label.text = f"Игр: {games_played}"
        self.earned_label.text = f"Монет: {total_earned} AC"


class FullscreenCountdownOverlay(FloatLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._active = False
        with self.canvas.before:
            self._shade_color = Color(0, 0, 0, 0.78)
            self._shade_rect = Rectangle(pos=self.pos, size=self.size)

        self._label = Label(
            text="",
            font_name="BrandFont",
            font_size=sp(132),
            color=(1, 1, 1, 1),
            halign="center",
            valign="middle",
        )
        self.add_widget(self._label)
        self.bind(pos=self._sync_canvas, size=self._sync_canvas)
        self.hide()

    def _sync_canvas(self, *_):
        self._shade_rect.pos = self.pos
        self._shade_rect.size = self.size
        self._label.pos = self.pos
        self._label.size = self.size
        self._label.text_size = self.size

    def show(self, seconds_left):
        self._active = True
        self.opacity = 1
        number = max(1, int(seconds_left))
        self._label.text = str(number)

    def hide(self):
        self._active = False
        self.opacity = 0
        self._label.text = ""

    def on_touch_down(self, touch):
        if not self._active:
            return False
        return True

    def on_touch_move(self, touch):
        if not self._active:
            return False
        return True

    def on_touch_up(self, touch):
        if not self._active:
            return False
        return True


class RoomScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        register_game_font()
        self.disabled = True

        self.room_code = ""
        self.room_state = {}
        self._poll_event = None
        self._voice_ui_event = None
        self._last_voice_ping_ts = 0.0
        self._last_chat_signature = None
        self._leave_sent = False
        self.voice_engine = RoomVoiceEngine()

        root = ScreenBackground(variant="game")
        content = BoxLayout(
            orientation="vertical",
            padding=[dp(14), dp(18), dp(14), dp(14)],
            spacing=dp(8),
        )

        top_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(54))
        self.back_btn = AppButton(text="В меню", compact=True, size_hint=(None, None), size=(dp(132), dp(50)))
        self.back_btn.bind(on_release=self._go_back_to_menu)
        top_row.add_widget(self.back_btn)
        top_row.add_widget(Widget())
        self.coin_badge = CoinBadge(size=(dp(122), dp(50)))
        top_row.add_widget(self.coin_badge)
        content.add_widget(top_row)

        self.room_meta_wrap_height = dp(22)
        self.room_meta_wrap = BoxLayout(orientation="horizontal", size_hint_y=None, height=self.room_meta_wrap_height)
        self.room_meta_label = BodyLabel(center=True, color=COLORS["text_muted"], font_size=sp(11), size_hint_y=None, text="")
        self.room_meta_wrap.add_widget(self.room_meta_label)
        content.add_widget(self.room_meta_wrap)
        content.add_widget(BrandTitle(text="ALIAS ONLINE", height=dp(82), font_size=sp(38), shadow_step=dp(3)))

        self.explainer_status_label = BodyLabel(
            center=True,
            color=COLORS["accent"],
            font_size=sp(12),
            size_hint_y=None,
            text="Ведущий: -- | Микрофон: --",
        )
        content.add_widget(self.explainer_status_label)

        self.players_wrap_height = dp(206)
        self.players_wrap = RoundedPanel(
            orientation="vertical",
            spacing=dp(8),
            padding=[dp(12), dp(10), dp(12), dp(10)],
            size_hint_y=None,
            height=self.players_wrap_height,
        )
        self.players_wrap.add_widget(PixelLabel(text="Игроки в комнате", center=True, font_size=sp(13), size_hint_y=None))
        self.players_scroll = ScrollView(do_scroll_x=False, bar_width=dp(4), scroll_type=["bars", "content"])
        self.players_box = GridLayout(
            cols=3,
            spacing=dp(6),
            padding=[dp(2), dp(2), dp(2), dp(2)],
            size_hint=(None, None),
            row_default_height=dp(78),
            row_force_default=True,
            col_default_width=dp(96),
            col_force_default=True,
        )
        self.players_box.bind(minimum_height=self.players_box.setter("height"))
        self.players_scroll.bind(width=self._sync_players_grid_width)
        self.players_scroll.add_widget(self.players_box)
        self.players_wrap.add_widget(self.players_scroll)
        content.add_widget(self.players_wrap)

        self.scores_wrap_height = dp(174)
        self.scores_wrap = BoxLayout(orientation="horizontal", size_hint_y=None, height=self.scores_wrap_height)
        self.scores_wrap.add_widget(Widget())
        self.score_badge = ScoreBadge()
        self.scores_wrap.add_widget(self.score_badge)
        self.scores_wrap.add_widget(Widget())
        content.add_widget(self.scores_wrap)

        self.players_summary_wrap_height = dp(24)
        self.players_summary_wrap = BoxLayout(orientation="horizontal", size_hint_y=None, height=self.players_summary_wrap_height)
        self.players_label = BodyLabel(center=True, color=COLORS["text_muted"], font_size=sp(11), size_hint_y=None, text="")
        self.players_summary_wrap.add_widget(self.players_label)
        content.add_widget(self.players_summary_wrap)

        self.lobby_start_height = dp(52)
        self.lobby_start_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=self.lobby_start_height)
        self.lobby_start_row.add_widget(Widget())
        self.start_game_btn = AppButton(
            text="Начать игру",
            compact=True,
            font_size=sp(14),
            size_hint=(None, None),
            size=(dp(228), dp(46)),
        )
        self.start_game_btn.bind(on_release=self._start_game)
        self.lobby_start_row.add_widget(self.start_game_btn)
        self.lobby_start_row.add_widget(Widget())
        content.add_widget(self.lobby_start_row)

        self.phase_wrap_height = dp(24)
        self.phase_wrap = BoxLayout(orientation="horizontal", size_hint_y=None, height=self.phase_wrap_height)
        self.phase_label = BodyLabel(center=True, color=COLORS["warning"], font_size=sp(12), size_hint_y=None, text="")
        self.phase_wrap.add_widget(self.phase_label)
        content.add_widget(self.phase_wrap)

        self.word_card_height = dp(188)
        self.word_card = SwipeWordCard(
            swipe_callback=self._handle_word_swipe,
            orientation="vertical",
            size_hint_y=None,
            height=self.word_card_height,
            spacing=dp(0),
            padding=[dp(14), dp(10), dp(14), dp(10)],
            bg_color=(1.0, 0.95, 0.36, 0.98),
            shadow_alpha=0.16,
        )
        self.word_card._border_color.rgba = COLORS["button"]
        self.word_card._border_line.width = 2.2
        self.word_label = Label(
            text="...",
            font_name="BrandFont",
            font_size=sp(78),
            color=(0.05, 0.09, 0.15, 1),
            halign="center",
            valign="middle",
        )
        self.word_label.bind(size=self._sync_word_label)
        self.word_card.add_widget(self.word_label)
        self.skip_word_btn = AppButton(
            text="Скип слова (-1)",
            compact=True,
            font_size=sp(13),
            size_hint=(None, None),
            size=(dp(228), dp(42)),
        )
        self.skip_word_btn.bind(on_release=self._skip_word)
        content.add_widget(self.word_card)

        self.voice_card_height = dp(96)
        self.voice_card = RoundedPanel(
            orientation="vertical",
            size_hint_y=None,
            height=self.voice_card_height,
            spacing=dp(4),
            padding=[dp(14), dp(8), dp(14), dp(8)],
        )

        mic_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(72))
        mic_row.add_widget(Widget())
        self.mic_button = VoiceMicButton()
        self.mic_button.bind(on_release=self._toggle_mic)
        mic_row.add_widget(self.mic_button)
        mic_row.add_widget(Widget())
        self.voice_card.add_widget(mic_row)
        self.voice_status = BodyLabel(center=True, color=COLORS["text_muted"], font_size=sp(11), size_hint_y=None, text="")
        content.add_widget(self.voice_card)

        chat_card = RoundedPanel(
            orientation="vertical",
            size_hint_y=1,
            spacing=dp(8),
            padding=[dp(14), dp(12), dp(14), dp(12)],
        )
        chat_card.add_widget(PixelLabel(text="Текстовый чат", center=True, font_size=sp(13), size_hint_y=None))

        self.chat_scroll = ScrollView(do_scroll_x=False, bar_width=dp(4), scroll_type=["bars", "content"])
        self.chat_box = BoxLayout(orientation="vertical", spacing=dp(6), size_hint_y=None)
        self.chat_box.bind(minimum_height=self.chat_box.setter("height"))
        self.chat_scroll.add_widget(self.chat_box)
        chat_card.add_widget(self.chat_scroll)

        self.chat_input_row = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(48))
        self.chat_input = AppTextInput(hint_text="Пиши догадку в чат...", height=dp(46))
        self.chat_input_row.add_widget(self.chat_input)
        self.send_btn = AppButton(text="Отправить", compact=True, font_size=sp(13), size_hint=(None, None), size=(dp(130), dp(46)))
        self.send_btn.bind(on_release=self._send_chat_message)
        self.chat_input_row.add_widget(self.send_btn)
        chat_card.add_widget(self.chat_input_row)

        self.status_label = BodyLabel(
            center=True,
            color=COLORS["text_muted"],
            font_size=sp(11),
            size_hint_y=None,
            text="Ведущий запускает игру, затем объясняет слова голосом.",
        )
        chat_card.add_widget(self.status_label)
        content.add_widget(chat_card)

        self.countdown_overlay = FullscreenCountdownOverlay()

        root.add_widget(content)
        root.add_widget(self.countdown_overlay)
        self.add_widget(root)

    def on_pre_enter(self, *_):
        self.disabled = False
        app = App.get_running_app()
        room_data = app.get_active_room() if app is not None else {}
        self.room_code = (room_data or {}).get("code", "")
        self._last_voice_ping_ts = 0.0
        self._last_chat_signature = None
        self._leave_sent = False
        self.mic_button.set_muted(True)
        self.mic_button.set_level(0.0)
        self.coin_badge.refresh_from_session()
        self.countdown_overlay.hide()
        self._start_polling()
        self._start_voice_ui_sync()
        self._start_voice_engine()
        self._poll_state()

    def on_leave(self, *_):
        self._stop_polling()
        self._stop_voice_ui_sync()
        self._stop_voice_engine()
        self.countdown_overlay.hide()
        self._leave_room()
        self.disabled = True

    def _go_back_to_menu(self, *_):
        self.manager.current = "start"

    def _leave_room(self):
        if self._leave_sent:
            return

        app = App.get_running_app()
        room_code = self.room_code or ((app.get_active_room() if app is not None else {}) or {}).get("code", "")
        player_name = self._player_name()
        self._leave_sent = True

        if room_code and player_name:
            try:
                leave_online_room(room_code=room_code, player_name=player_name)
            except (ConnectionError, ValueError):
                pass

        self.room_code = ""
        self.room_state = {}
        self._last_chat_signature = None
        if app is not None:
            app.clear_active_room()

    def _sync_word_label(self, *_):
        self.word_label.text_size = (max(0, self.word_label.width - dp(12)), max(0, self.word_label.height - dp(12)))

    def _handle_word_swipe(self, _direction):
        if self._current_phase() == "round" and self._is_explainer():
            self._skip_word()

    def _player_name(self):
        app = App.get_running_app()
        return app.resolve_player_name() if app is not None else None

    def _normalized_player_name(self, value):
        return (value or "").strip().lower()

    def _same_player(self, left, right):
        return bool(self._normalized_player_name(left) and self._normalized_player_name(left) == self._normalized_player_name(right))

    def _current_phase(self):
        phase = (self.room_state.get("game_phase") or "").strip().lower()
        if phase in {"lobby", "countdown", "round"}:
            return phase
        room_phase = (self.room_state.get("room", {}).get("game_phase") or "").strip().lower()
        if room_phase in {"lobby", "countdown", "round"}:
            return room_phase
        return "lobby"

    def _is_explainer(self):
        room = self.room_state.get("room", {})
        return self._same_player(self._player_name(), room.get("current_explainer"))

    def _is_host(self):
        room = self.room_state.get("room", {})
        return self._same_player(self._player_name(), room.get("host_name"))

    def _can_start_game(self):
        return self._current_phase() == "lobby" and bool(self._player_name())

    def _sync_players_grid_width(self, *_):
        cols = max(1, int(getattr(self.players_box, "cols", 1) or 1))
        total_spacing = dp(6) * (cols - 1)
        total_padding = dp(4)
        available_width = max(dp(96), self.players_scroll.width - dp(12))
        column_width = max(dp(86), (available_width - total_spacing - total_padding) / cols)
        self.players_box.col_default_width = column_width
        self.players_box.width = column_width * cols + total_spacing + total_padding

    def _start_polling(self):
        self._stop_polling()
        self._poll_event = Clock.schedule_interval(lambda _dt: self._poll_state(), 1.0)

    def _stop_polling(self):
        if self._poll_event is not None:
            self._poll_event.cancel()
            self._poll_event = None

    def _start_voice_ui_sync(self):
        self._stop_voice_ui_sync()
        self._voice_ui_event = Clock.schedule_interval(lambda _dt: self._sync_voice_ui(), 0.12)

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
            should_transmit=lambda: self._is_explainer() and self._current_phase() == "round" and not self.mic_button.muted,
        )
        self.voice_engine.set_muted(self.mic_button.muted)

    def _stop_voice_engine(self):
        self.voice_engine.stop()

    def _set_button_visibility(self, button, visible):
        button.disabled = not visible
        button.opacity = 1 if visible else 0

    def _set_panel_visibility(self, panel, visible, shown_height):
        panel.disabled = not visible
        panel.opacity = 1 if visible else 0
        panel.height = shown_height if visible else dp(0)

    def _show_explainer_controls(self, is_explainer, phase):
        can_start_game = phase == "lobby" and self._can_start_game()
        self._set_button_visibility(self.start_game_btn, can_start_game)
        self._set_button_visibility(self.skip_word_btn, is_explainer and phase == "round")

    def _set_chat_input_visibility(self, visible):
        row_height = dp(48) if visible else dp(0)
        self.chat_input_row.height = row_height
        self.chat_input_row.opacity = 1 if visible else 0
        self.chat_input_row.disabled = not visible
        self.chat_input.disabled = not visible
        self.send_btn.disabled = not visible

    def _render_player_cards(self, players, explainer_name):
        self.players_box.clear_widgets()
        self.players_box.cols = 1 if not players else max(1, min(3, len(players)))
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

        profile_map = {}
        try:
            for profile in list_profiles():
                profile_map[profile.name.strip().lower()] = profile
        except Exception:
            profile_map = {}

        for listed_player in players:
            card = LobbyPlayerCard()
            card.width = self.players_box.col_default_width
            profile = profile_map.get((listed_player or "").strip().lower())
            card.set_player(listed_player, profile, is_explainer=self._same_player(listed_player, explainer_name))
            self.players_box.add_widget(card)

    def _poll_state(self):
        if not self.room_code:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Комната не выбрана. Создай комнату или зайди в существующую."
            return

        player_name = self._player_name()
        if not player_name:
            self.status_label.color = COLORS["error"]
            self.status_label.text = "Сессия не найдена. Войди в аккаунт заново."
            return

        try:
            state = get_online_room_state(room_code=self.room_code, player_name=player_name)
        except ConnectionError as error:
            self.status_label.color = COLORS["error"]
            self.status_label.text = str(error)
            return
        except ValueError as error:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = str(error)
            return

        self.room_state = state
        app = App.get_running_app()
        if app is not None:
            app.set_active_room(state.get("room", {}))
        self._apply_state()

    def _apply_state(self):
        room = self.room_state.get("room", {})
        players = self.room_state.get("players", [])
        scores = self.room_state.get("scores", [])
        messages = self.room_state.get("messages", [])

        player_name = self._player_name() or ""
        is_explainer = self._same_player(player_name, room.get("current_explainer"))
        phase = self._current_phase()
        countdown_left = int(self.room_state.get("countdown_left_sec") or 0)
        round_left = int(self.room_state.get("round_left_sec") or 0)
        explainer_name = room.get("current_explainer") or "—"

        room_name = room.get("room_name", "Комната")
        code = room.get("code", self.room_code)
        players_text = f"{room.get('players_count', '?')}/{room.get('max_players', '?')}"
        self.room_meta_label.text = f"{room_name} | Код: {code} | Игроков: {players_text}"

        explainer_can_only_voice = is_explainer and phase == "round"

        if explainer_can_only_voice:
            self.word_label.text = self.room_state.get("current_word") or "..."
            self.chat_input.hint_text = "Ведущий не пишет в чат."
            self._set_chat_input_visibility(False)
            self.mic_button.set_enabled(True)
        else:
            self.word_label.text = "Слово скрыто"
            self.chat_input.hint_text = "Пиши догадку в чат..." if phase == "round" else "Сообщение в чат..."
            self._set_chat_input_visibility(True)
            self.mic_button.set_enabled(False)
            self.mic_button.set_muted(True)
            self.voice_engine.set_muted(True)

        voice_active = bool(self.room_state.get("voice_active"))
        voice_speaker = self.room_state.get("voice_speaker")
        if phase != "round":
            mic_state_text = "ожидает старт"
        elif not self.voice_engine.available and is_explainer:
            mic_state_text = "недоступен"
        elif voice_active and voice_speaker == explainer_name:
            mic_state_text = "говорит"
        elif is_explainer and self.mic_button.muted:
            mic_state_text = "выключен"
        elif is_explainer and not self.mic_button.muted:
            mic_state_text = "включен"
        else:
            mic_state_text = "молчит"
        if phase == "lobby":
            self.explainer_status_label.text = f"Ведущий после старта: {explainer_name}"
        else:
            self.explainer_status_label.text = f"Ведущий: {explainer_name} | Микрофон: {mic_state_text}"

        self._show_explainer_controls(is_explainer, phase)
        self._set_panel_visibility(self.room_meta_wrap, phase != "lobby", self.room_meta_wrap_height)
        self._set_panel_visibility(self.players_wrap, phase == "lobby", self.players_wrap_height)
        self._set_panel_visibility(self.players_summary_wrap, phase != "lobby", self.players_summary_wrap_height)
        self._set_panel_visibility(
            self.lobby_start_row,
            phase == "lobby" and self._can_start_game(),
            self.lobby_start_height,
        )
        self._set_panel_visibility(self.word_card, phase == "round" and is_explainer, self.word_card_height)
        self._set_panel_visibility(self.voice_card, phase == "round" and is_explainer, self.voice_card_height)
        self._set_panel_visibility(self.scores_wrap, phase == "round", self.scores_wrap_height)
        self._set_panel_visibility(self.phase_wrap, phase in {"countdown", "round"}, self.phase_wrap_height)

        if phase == "lobby":
            self.phase_label.text = ""
            self.countdown_overlay.hide()
            self.status_label.color = COLORS["text_muted"]
            self.status_label.text = "Лобби: общайтесь в чате, пока ведущий не начнет игру."
        elif phase == "countdown":
            self.phase_label.color = COLORS["accent"]
            self.phase_label.text = f"Игра начнется через {countdown_left} сек"
            if countdown_left > 0:
                self.countdown_overlay.show(countdown_left)
            else:
                self.countdown_overlay.show(1)
            self.status_label.color = COLORS["accent"]
            self.status_label.text = "Подготовьтесь, раунд сейчас начнется."
        else:
            self.phase_label.color = COLORS["success"]
            self.phase_label.text = f"Раунд: осталось {round_left} сек"
            self.countdown_overlay.hide()
            if is_explainer:
                self.status_label.color = COLORS["text_muted"]
                self.status_label.text = "Объясняй слово голосом. Свайпни карточку вверх или вниз, чтобы скипнуть."
            else:
                self.status_label.color = COLORS["text_muted"]
                self.status_label.text = "Пиши догадки в чат. За верное слово ты тоже получаешь +1."

        if players:
            self.players_label.text = "Игроки: " + ", ".join(players)
        else:
            self.players_label.text = "Игроки: пока нет данных"
        self._render_player_cards(players, explainer_name)

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

        self._render_messages(messages)

    def _sync_profile_progress(self, current_score, phase, role):
        app = App.get_running_app()
        if app is None or not getattr(app, "authenticated", False) or not self.room_code:
            return

        profile = app.current_profile()
        if profile is None:
            return

        sync_room_progress(
            email=profile.email,
            room_code=self.room_code,
            current_score=current_score,
            round_started=phase == "round",
            role=role,
        )

    def _render_messages(self, messages):
        signature = tuple(
            (message.get("id"), message.get("message_type"), message.get("player_name"), message.get("message"))
            for message in messages
        )
        if signature == self._last_chat_signature:
            return
        self._last_chat_signature = signature

        previous_scroll_y = self.chat_scroll.scroll_y
        was_near_bottom = previous_scroll_y <= 0.04
        self.chat_box.clear_widgets()

        if not messages:
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

        for message in messages:
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
                    font_size=sp(12),
                    size_hint_y=None,
                )
            )

        target_scroll = 0 if was_near_bottom else previous_scroll_y
        Clock.schedule_once(lambda *_: setattr(self.chat_scroll, "scroll_y", target_scroll), 0)

    def _start_game(self, *_):
        if self._current_phase() != "lobby":
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Игра уже запущена."
            return

        player_name = self._player_name()
        if not player_name:
            self.status_label.color = COLORS["error"]
            self.status_label.text = "Не удалось определить игрока для старта игры."
            return

        try:
            start_response = start_room_game(room_code=self.room_code, player_name=player_name)
        except ConnectionError as error:
            self.status_label.color = COLORS["error"]
            self.status_label.text = str(error)
            return
        except ValueError as error:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = str(error)
            return

        if isinstance(start_response, dict):
            updated_state = dict(self.room_state or {})
            room_payload = start_response.get("room")
            if isinstance(room_payload, dict) and room_payload:
                updated_state["room"] = room_payload
            phase = (start_response.get("game_phase") or "").strip().lower()
            if phase in {"lobby", "countdown", "round"}:
                updated_state["game_phase"] = phase
            if "countdown_left_sec" in start_response:
                updated_state["countdown_left_sec"] = int(start_response.get("countdown_left_sec") or 0)
            if "round_left_sec" in start_response:
                updated_state["round_left_sec"] = int(start_response.get("round_left_sec") or 0)
            self.room_state = updated_state
            self._apply_state()

        self.status_label.color = COLORS["success"]
        self.status_label.text = "Старт игры! На экране общий отсчет 10 секунд."
        self._poll_state()

    def _send_chat_message(self, *_):
        if self._is_explainer() and self._current_phase() == "round":
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Ведущий не может писать в чат. Только объяснять голосом."
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
        try:
            if phase == "round":
                result = send_room_guess(room_code=self.room_code, player_name=player_name, guess=text)
                if result.get("correct"):
                    awarded_player = result.get("awarded_player") or "ведущий"
                    guesser_player = result.get("guesser_player") or player_name
                    self.status_label.color = COLORS["success"]
                    self.status_label.text = f"Верно! {awarded_player} +1 и {guesser_player} +1."
                else:
                    self.status_label.color = COLORS["text_muted"]
                    self.status_label.text = "Догадка отправлена."
            else:
                send_room_chat(room_code=self.room_code, player_name=player_name, message=text)
                self.status_label.color = COLORS["success"]
                self.status_label.text = "Сообщение отправлено."
        except ConnectionError as error:
            self.status_label.color = COLORS["error"]
            self.status_label.text = str(error)
            return
        except ValueError as error:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = str(error)
            return

        self.chat_input.text = ""
        self._poll_state()

    def _skip_word(self, *_):
        if not self._is_explainer():
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Скипать слова может только ведущий."
            return
        if self._current_phase() != "round":
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Скип доступен только во время раунда."
            return

        player_name = self._player_name()
        try:
            response = skip_room_word(room_code=self.room_code, player_name=player_name)
        except ConnectionError as error:
            self.status_label.color = COLORS["error"]
            self.status_label.text = str(error)
            return
        except ValueError as error:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = str(error)
            return

        self.status_label.color = COLORS["warning"]
        self.status_label.text = f"Слово скипнуто. Штраф {response.get('delta', -1)}."
        self._poll_state()

    def _toggle_mic(self, *_):
        if not self._is_explainer():
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Микрофон активен только у ведущего."
            return

        new_muted = not self.mic_button.muted
        self.mic_button.set_muted(new_muted)
        self.voice_engine.set_muted(new_muted)
        if new_muted:
            self.status_label.color = COLORS["text_muted"]
            self.status_label.text = "Микрофон выключен."
        else:
            self.status_label.color = COLORS["success"]
            self.status_label.text = "Микрофон включен."

    def _sync_voice_ui(self):
        if not self.voice_engine.available:
            self.mic_button.set_level(0.0)
            return

        level = self.voice_engine.level() if self.voice_engine.active() else 0.0
        if self.mic_button.muted:
            level = 0.0
        self.mic_button.set_level(level)

        if not self._is_explainer() or self.mic_button.muted or self._current_phase() != "round":
            return

        if level < 0.06:
            return

        now_ts = time.time()
        if now_ts - self._last_voice_ping_ts < 0.7:
            return

        self._last_voice_ping_ts = now_ts
        player_name = self._player_name()
        if not player_name:
            return

        try:
            ping_room_voice(room_code=self.room_code, player_name=player_name, active_seconds=3)
        except (ConnectionError, ValueError):
            pass
