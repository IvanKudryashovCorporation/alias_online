import time

from kivy.app import App
from kivy.animation import Animation
from kivy.clock import Clock
from kivy.graphics import (
    Color,
    Ellipse,
    Line,
    Rectangle,
    RoundedRectangle,
    StencilPop,
    StencilPush,
    StencilUnUse,
    StencilUse,
)
from kivy.metrics import dp, sp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from services import (
    RoomVoiceEngine,
    get_online_room_state,
    join_online_room,
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
        button_size = kwargs.pop("size", (dp(62), dp(62)))
        button_size_hint = kwargs.pop("size_hint", (None, None))
        super().__init__(size_hint=button_size_hint, size=button_size, **kwargs)
        self._muted = True
        self._enabled = True
        self._level = 0.0

        with self.canvas.before:
            self._shadow_color = Color(0, 0, 0, 0.22)
            self._shadow = Ellipse(pos=self.pos, size=self.size)
            self._bg_color = Color(0.08, 0.13, 0.21, 0.96)
            self._bg = Ellipse(pos=self.pos, size=self.size)

            self._mic_color = Color(0.96, 0.98, 1.0, 1.0)
            self._head = Ellipse()
            self._body = RoundedRectangle(radius=[dp(6)] * 4)

            StencilPush()
            self._fill_mask_color = Color(1, 1, 1, 1)
            self._fill_mask_head = Ellipse()
            self._fill_mask_body = RoundedRectangle(radius=[dp(6)] * 4)
            StencilUse()
            self._fill_color = Color(0.22, 0.90, 0.42, 0.0)
            self._fill_rect = Rectangle()
            StencilUnUse()
            self._fill_mask_release_head = Ellipse()
            self._fill_mask_release_body = RoundedRectangle(radius=[dp(6)] * 4)
            StencilPop()

            self._cradle = Line(width=dp(2.2), ellipse=(0, 0, 0, 0, 205, 335))
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
        if not self._enabled:
            self._level = 0.0
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
            self._fill_color.rgba = (0.22, 0.90, 0.42, 0.0)
            self._outline_color.rgba = (1, 1, 1, 0.08)
            self._mute_color.rgba = (0.96, 0.23, 0.23, 0.42)
        else:
            if self._muted:
                self._bg_color.rgba = (0.08, 0.13, 0.21, 0.96)
                self._mic_color.rgba = (0.96, 0.98, 1.0, 1.0)
                self._fill_color.rgba = (0.22, 0.90, 0.42, 0.0)
                self._outline_color.rgba = (1, 1, 1, 0.16)
            else:
                level = self._level
                glow_alpha = 0.16 + level * 0.30
                self._bg_color.rgba = (0.08, 0.13, 0.21, 0.96)
                self._mic_color.rgba = (0.96, 0.98, 1.0, 1.0)
                self._fill_color.rgba = (0.22, 0.90, 0.42, 0.28 + level * 0.72)
                self._outline_color.rgba = (0.44, 0.94, 0.58, glow_alpha)
            self._mute_color.rgba = (0.96, 0.23, 0.23, 0.95 if self._muted else 0.0)

        self._sync_canvas()

    def _sync_canvas(self, *_):
        self._shadow.pos = (self.x, self.y - dp(1.5))
        self._shadow.size = self.size
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._outline.ellipse = (self.x, self.y, self.width, self.height)

        head_w = self.width * 0.28
        head_h = self.height * 0.28
        head_x = self.center_x - head_w / 2
        head_y = self.y + self.height * 0.48
        self._head.pos = (head_x, head_y)
        self._head.size = (head_w, head_h)
        self._fill_mask_head.pos = self._head.pos
        self._fill_mask_head.size = self._head.size
        self._fill_mask_release_head.pos = self._head.pos
        self._fill_mask_release_head.size = self._head.size

        body_w = self.width * 0.20
        body_h = self.height * 0.16
        body_x = self.center_x - body_w / 2
        body_y = self.y + self.height * 0.36
        self._body.pos = (body_x, body_y)
        self._body.size = (body_w, body_h)
        self._fill_mask_body.pos = self._body.pos
        self._fill_mask_body.size = self._body.size
        self._fill_mask_release_body.pos = self._body.pos
        self._fill_mask_release_body.size = self._body.size

        fill_w = max(head_w, body_w)
        fill_x = self.center_x - fill_w / 2
        fill_bottom = body_y
        fill_top = head_y + head_h
        fill_h = max(0.0, (fill_top - fill_bottom) * self._level)
        self._fill_rect.pos = (fill_x, fill_bottom)
        self._fill_rect.size = (fill_w, fill_h)

        cradle_w = self.width * 0.36
        cradle_h = self.height * 0.38
        cradle_x = self.center_x - cradle_w / 2
        cradle_y = self.y + self.height * 0.30
        self._cradle.ellipse = (cradle_x, cradle_y, cradle_w, cradle_h, 205, 335)

        stem_w = self.width * 0.05
        stem_h = self.height * 0.08
        self._stem.pos = (self.center_x - stem_w / 2, self.y + self.height * 0.25)
        self._stem.size = (stem_w, stem_h)

        base_w = self.width * 0.26
        base_h = self.height * 0.04
        self._base.pos = (self.center_x - base_w / 2, self.y + self.height * 0.18)
        self._base.size = (base_w, base_h)

        self._mute_line.points = [
            self.x + self.width * 0.26,
            self.y + self.height * 0.24,
            self.x + self.width * 0.74,
            self.y + self.height * 0.76,
        ]


class SwipeWordCard(RoundedPanel):
    def __init__(self, swipe_callback=None, swipe_threshold=44, **kwargs):
        self._swipe_callback = swipe_callback
        self._swipe_start = None
        self._home_pos = None
        self._animating = False
        self._swipe_threshold = dp(swipe_threshold)
        super().__init__(**kwargs)

    def set_swipe_callback(self, callback):
        self._swipe_callback = callback

    def on_touch_down(self, touch):
        if getattr(self, "disabled", False) or not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        Animation.cancel_all(self)
        self._swipe_start = touch.pos
        self._home_pos = self.pos
        touch.grab(self)
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is not self or self._home_pos is None or self._animating:
            return super().on_touch_move(touch)

        delta_x = touch.x - self._swipe_start[0]
        delta_y = touch.y - self._swipe_start[1]
        if abs(delta_y) >= abs(delta_x):
            self.y = self._home_pos[1] + delta_y * 0.42
            fade = min(0.55, abs(delta_y) / max(dp(1), self.height * 1.1))
            self.opacity = 1.0 - fade
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
            self.animate_swipe_out("up" if delta_y > 0 else "down", callback=self._swipe_callback)
        else:
            self.animate_back_home()
        return True

    def animate_back_home(self):
        if self._home_pos is None:
            return
        Animation.cancel_all(self)
        Animation(y=self._home_pos[1], opacity=1.0, d=0.12, t="out_quad").start(self)

    def animate_swipe_out(self, direction, callback=None):
        if self._home_pos is None or self._animating:
            return

        self._animating = True
        home_x, home_y = self._home_pos
        target_y = home_y + (self.height * 1.75 if direction == "up" else -self.height * 1.75)

        Animation.cancel_all(self)
        animation = Animation(y=target_y, opacity=0.0, d=0.16, t="out_quad")

        def _finish(*_):
            self.pos = (home_x, home_y)
            self.opacity = 1.0
            self._animating = False
            if callback is not None:
                callback(direction)

        animation.bind(on_complete=_finish)
        animation.start(self)


class ScoreCircleWidget(FloatLayout):
    def __init__(self, **kwargs):
        super().__init__(size_hint=(None, None), size=(dp(104), dp(104)), **kwargs)
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
            font_size=sp(44),
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
            spacing=dp(2),
            size_hint=(None, None),
            size=(dp(160), dp(128)),
            **kwargs,
        )
        self.caption = PixelLabel(text="СЧЕТ:", center=True, font_size=sp(17), size_hint_y=None)
        self.add_widget(self.caption)

        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(108))
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
            spacing=dp(1),
            padding=[dp(5), dp(5), dp(5), dp(5)],
            size_hint_x=None,
            size_hint_y=None,
            height=dp(98),
            bg_color=COLORS["surface_panel"],
            shadow_alpha=0.14,
            **kwargs,
        )
        self.role_label = Label(
            text="",
            font_name="GameFont",
            font_size=sp(7.5),
            color=COLORS["accent"],
            halign="center",
            valign="middle",
            size_hint_y=None,
            height=0,
            opacity=0,
        )
        self.role_label.bind(size=lambda *_: setattr(self.role_label, "text_size", self.role_label.size))
        self.add_widget(self.role_label)

        self.name_label = PixelLabel(
            text="",
            center=True,
            font_size=sp(9.2),
            size_hint_y=None,
            shorten=True,
            shorten_from="right",
            max_lines=1,
        )
        self.add_widget(self.name_label)

        avatar_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(24))
        avatar_row.add_widget(Widget())
        self.avatar = AvatarButton()
        self.avatar.size = (dp(24), dp(24))
        self.avatar.disabled = True
        avatar_row.add_widget(self.avatar)
        avatar_row.add_widget(Widget())
        self.add_widget(avatar_row)

        text_col = BoxLayout(orientation="vertical", spacing=dp(1), size_hint_y=None, height=dp(32))
        self.games_label = BodyLabel(text="", center=True, color=COLORS["text_soft"], font_size=sp(7.8), size_hint_y=None)
        text_col.add_widget(self.games_label)
        self.earned_label = BodyLabel(text="", center=True, color=COLORS["accent"], font_size=sp(7.8), size_hint_y=None)
        text_col.add_widget(self.earned_label)
        self.add_widget(text_col)

    def set_player(self, player_name, profile, is_explainer=False, is_self=False, room_score=0, phase="lobby"):
        self.avatar.set_profile(profile)
        games_played = getattr(profile, "games_played", 0) if profile is not None else 0
        total_earned = getattr(profile, "total_points", 0) if profile is not None else 0
        display_name = player_name or "Игрок"
        role_tags = []
        if is_explainer:
            role_tags.append("ОБЪЯСНЯЕТ")
        if is_self:
            role_tags.append("ТЫ")

        self.name_label.text = display_name
        if phase == "round":
            self.games_label.text = f"Очки: {int(room_score or 0)}"
            self.earned_label.text = "В этой комнате"
        else:
            self.games_label.text = f"Игр: {games_played}"
            self.earned_label.text = f"Монет: {total_earned} AC"
        if role_tags:
            self.role_label.text = " • ".join(role_tags)
            self.role_label.height = dp(12)
            self.role_label.opacity = 1
        else:
            self.role_label.text = ""
            self.role_label.height = 0
            self.role_label.opacity = 0

        if is_explainer:
            self._bg_color.rgba = (0.19, 0.27, 0.39, 0.98)
            self._border_color.rgba = COLORS["accent"]
            self._border_line.width = 2.0
            self.name_label.color = COLORS["accent"]
            self.role_label.color = COLORS["accent"]
        elif is_self:
            self._bg_color.rgba = (0.15, 0.23, 0.35, 0.98)
            self._border_color.rgba = COLORS["button"]
            self._border_line.width = 1.8
            self.name_label.color = COLORS["text"]
            self.role_label.color = COLORS["button"]
        else:
            self._bg_color.rgba = COLORS["surface_panel"]
            self._border_color.rgba = COLORS["outline"]
            self._border_line.width = 1.2
            self.name_label.color = COLORS["text"]
            self.role_label.color = COLORS["accent"]


class RoundPlayerRow(RoundedPanel):
    def __init__(self, **kwargs):
        super().__init__(
            orientation="horizontal",
            spacing=dp(8),
            padding=[dp(10), dp(6), dp(10), dp(6)],
            size_hint_x=None,
            size_hint_y=None,
            height=dp(44),
            bg_color=COLORS["surface_panel"],
            shadow_alpha=0.10,
            **kwargs,
        )
        self.avatar = AvatarButton()
        self.avatar.size = (dp(24), dp(24))
        self.avatar.disabled = True
        self.add_widget(self.avatar)

        self.name_label = PixelLabel(
            text="",
            font_size=sp(10.5),
            size_hint=(1, 1),
            center=False,
            shorten=True,
            shorten_from="right",
            max_lines=1,
        )
        self.add_widget(self.name_label)

        self.score_label = PixelLabel(
            text="0",
            font_size=sp(12),
            center=True,
            size_hint=(None, 1),
            width=dp(62),
        )
        self.add_widget(self.score_label)

    def set_player(self, player_name, profile, room_score=0, is_explainer=False, is_self=False, phase="round"):
        self.avatar.set_profile(profile)
        badges = []
        if is_explainer:
            badges.append("ОБЪЯСН.")
        if is_self:
            badges.append("ТЫ")

        if badges:
            self.name_label.text = f"{player_name} • {' • '.join(badges)}"
        else:
            self.name_label.text = player_name or "Игрок"
        self.score_label.text = str(int(room_score or 0))

        if is_explainer:
            self._bg_color.rgba = (0.19, 0.27, 0.39, 0.98)
            self._border_color.rgba = COLORS["accent"]
            self._border_line.width = 1.8
            self.name_label.color = COLORS["accent"]
            self.score_label.color = COLORS["accent"]
        elif is_self:
            self._bg_color.rgba = (0.15, 0.23, 0.35, 0.98)
            self._border_color.rgba = COLORS["button"]
            self._border_line.width = 1.6
            self.name_label.color = COLORS["text"]
            self.score_label.color = COLORS["button"]
        else:
            self._bg_color.rgba = COLORS["surface_panel"]
            self._border_color.rgba = COLORS["outline"]
            self._border_line.width = 1.0
            self.name_label.color = COLORS["text"]
            self.score_label.color = COLORS["text_soft"]


class MiniStatChip(RoundedPanel):
    def __init__(self, title, **kwargs):
        super().__init__(
            orientation="vertical",
            spacing=dp(0),
            padding=[dp(6), dp(6), dp(6), dp(6)],
            size_hint=(1, None),
            height=dp(50),
            bg_color=(0.13, 0.18, 0.29, 0.98),
            shadow_alpha=0.10,
            **kwargs,
        )
        self.title_label = BodyLabel(text=title, center=True, color=COLORS["text_muted"], font_size=sp(8.5), size_hint_y=None)
        self.add_widget(self.title_label)
        self.value_label = PixelLabel(text="0", center=True, color=COLORS["accent"], font_size=sp(12), size_hint_y=None)
        self.add_widget(self.value_label)

    def set_value(self, value):
        self.value_label.text = str(value)


class ExplainerSpotlightCard(RoundedPanel):
    def __init__(self, **kwargs):
        super().__init__(
            orientation="vertical",
            spacing=dp(8),
            padding=[dp(12), dp(10), dp(12), dp(10)],
            size_hint_y=None,
            height=dp(138),
            **kwargs,
        )
        self.add_widget(PixelLabel(text="Объясняет сейчас", center=True, font_size=sp(13), size_hint_y=None))

        header_row = BoxLayout(orientation="horizontal", spacing=dp(10), size_hint_y=None, height=dp(52))
        self.avatar = AvatarButton()
        self.avatar.disabled = True
        self.avatar.size = (dp(46), dp(46))
        header_row.add_widget(self.avatar)

        info_col = BoxLayout(orientation="vertical", spacing=dp(1))
        self.name_label = PixelLabel(text="—", font_size=sp(16), size_hint_y=None)
        info_col.add_widget(self.name_label)
        self.mic_label = BodyLabel(text="Микрофон: молчит", color=COLORS["text_soft"], font_size=sp(10.5), size_hint_y=None)
        info_col.add_widget(self.mic_label)
        header_row.add_widget(info_col)
        self.add_widget(header_row)

        stats_row = BoxLayout(orientation="horizontal", spacing=dp(6), size_hint_y=None, height=dp(50))
        self.games_chip = MiniStatChip("Игр")
        stats_row.add_widget(self.games_chip)
        self.explained_chip = MiniStatChip("Объясн.")
        stats_row.add_widget(self.explained_chip)
        self.guessed_chip = MiniStatChip("Угадано")
        stats_row.add_widget(self.guessed_chip)
        self.add_widget(stats_row)

    def set_explainer(self, explainer_name, profile, mic_state_text):
        self.avatar.set_profile(profile)
        self.name_label.text = explainer_name or "—"
        self.mic_label.text = f"Микрофон: {mic_state_text}"
        self.games_chip.set_value(getattr(profile, "games_played", 0) if profile is not None else 0)
        self.explained_chip.set_value(getattr(profile, "explained_words", 0) if profile is not None else 0)
        self.guessed_chip.set_value(getattr(profile, "guessed_words", 0) if profile is not None else 0)


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
        self._smoothed_voice_level = 0.0
        self._last_chat_signature = None
        self._leave_sent = False
        self.leave_confirm_popup = None
        self.voice_engine = RoomVoiceEngine()
        self._start_game_scheduled = False
        self._last_start_attempt_ts = 0.0
        self._start_game_request_in_flight = False

        root = ScreenBackground(variant="game")
        content = BoxLayout(
            orientation="vertical",
            padding=[dp(14), dp(18), dp(14), dp(14)],
            spacing=dp(8),
        )

        top_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(54))
        self.back_btn = AppButton(text="В меню", compact=True, size_hint=(None, None), size=(dp(132), dp(50)))
        self.back_btn.bind(on_release=self._go_back_to_menu)
        self._set_room_exit_button(False)
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
        self.brand_title_height = dp(82)
        self.brand_title = BrandTitle(
            text="ALIAS ONLINE",
            height=self.brand_title_height,
            font_size=sp(38),
            shadow_step=dp(3),
        )
        content.add_widget(self.brand_title)

        self.explainer_status_label = BodyLabel(
            center=True,
            color=COLORS["accent"],
            font_size=sp(12),
            size_hint_y=None,
            text="Объясняет слова: -- | Микрофон: --",
        )
        content.add_widget(self.explainer_status_label)

        self.players_wrap_height = dp(214)
        self.players_wrap_round_height = dp(176)
        self.players_wrap = RoundedPanel(
            orientation="vertical",
            spacing=dp(6),
            padding=[dp(10), dp(8), dp(10), dp(8)],
            size_hint_y=None,
            height=self.players_wrap_height,
        )
        self.players_wrap_title = PixelLabel(text="Игроки в комнате • 0/0", center=True, font_size=sp(13), size_hint_y=None)
        self.players_wrap.add_widget(self.players_wrap_title)
        self.players_scroll = ScrollView(do_scroll_x=False, bar_width=dp(4), scroll_type=["bars", "content"])
        self.players_box = GridLayout(
            cols=3,
            spacing=dp(5),
            padding=[dp(2), dp(2), dp(2), dp(2)],
            size_hint=(None, None),
            row_default_height=dp(102),
            row_force_default=True,
            col_default_width=dp(96),
            col_force_default=True,
        )
        self.players_box.bind(minimum_height=self.players_box.setter("height"))
        self.players_scroll.bind(width=self._sync_players_grid_width)
        self.players_scroll.add_widget(self.players_box)
        self.players_wrap.add_widget(self.players_scroll)
        content.add_widget(self.players_wrap)

        self.scores_wrap_height = dp(132)
        self.scores_wrap = BoxLayout(orientation="horizontal", size_hint_y=None, height=self.scores_wrap_height)
        self.scores_wrap.add_widget(Widget())
        self.score_badge = ScoreBadge()
        self.scores_wrap.add_widget(self.score_badge)
        self.scores_wrap.add_widget(Widget())
        content.add_widget(self.scores_wrap)

        self.players_summary_wrap_height = dp(56)
        self.players_summary_wrap = BoxLayout(orientation="horizontal", size_hint_y=None, height=self.players_summary_wrap_height)
        self.players_label = BodyLabel(center=True, color=COLORS["text_muted"], font_size=sp(11), size_hint_y=None, text="")
        self.players_summary_wrap.add_widget(self.players_label)
        self.players_summary_wrap.add_widget(Widget())
        self.mic_button_top = VoiceMicButton(size=(dp(48), dp(48)))
        self.mic_button_top.bind(on_release=self._toggle_mic)
        self.players_summary_wrap.add_widget(self.mic_button_top)
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
        self.start_game_btn.bind(on_press=self._queue_start_game, on_release=self._queue_start_game)
        self.lobby_start_row.add_widget(self.start_game_btn)
        self.lobby_start_row.add_widget(Widget())
        content.add_widget(self.lobby_start_row)

        self.phase_wrap_height = dp(24)
        self.phase_wrap = BoxLayout(orientation="horizontal", size_hint_y=None, height=self.phase_wrap_height)
        self.phase_label = BodyLabel(center=True, color=COLORS["warning"], font_size=sp(12), size_hint_y=None, text="")
        self.phase_wrap.add_widget(self.phase_label)
        content.add_widget(self.phase_wrap)

        self.explainer_card_height = dp(138)
        self.explainer_card = ExplainerSpotlightCard()
        self.explainer_card.height = self.explainer_card_height
        content.add_widget(self.explainer_card)

        self.word_card_height = dp(136)
        self.word_stage_height = dp(142)
        self.word_stage = FloatLayout(size_hint_y=None, height=self.word_stage_height)
        self.word_stage.bind(size=self._sync_word_stage_layout, pos=self._sync_word_stage_layout)
        self.word_card = SwipeWordCard(
            swipe_callback=self._handle_word_swipe,
            orientation="vertical",
            size_hint=(None, None),
            height=self.word_card_height,
            spacing=dp(0),
            padding=[dp(16), dp(8), dp(16), dp(8)],
            bg_color=(1.0, 0.95, 0.36, 0.98),
            shadow_alpha=0.16,
        )
        self.word_card._border_color.rgba = COLORS["button"]
        self.word_card._border_line.width = 2.2
        self.word_label = Label(
            text="...",
            font_name="GameFont",
            font_size=sp(56),
            color=(0.05, 0.09, 0.15, 1),
            halign="center",
            valign="middle",
        )
        self.word_label.bind(size=self._sync_word_label)
        self.word_card.add_widget(self.word_label)
        self.word_stage.add_widget(self.word_card)
        content.add_widget(self.word_stage)

        self.voice_card_height = dp(56)
        self.voice_card = RoundedPanel(
            orientation="horizontal",
            size_hint_y=None,
            height=self.voice_card_height,
            spacing=dp(10),
            padding=[dp(4), dp(0), dp(4), dp(0)],
            bg_color=(0, 0, 0, 0),
            shadow_alpha=0,
        )
        voice_text_col = BoxLayout(orientation="vertical", spacing=dp(0))
        voice_text_col.add_widget(PixelLabel(text="Микрофон", font_size=sp(11), size_hint_y=None))
        self.voice_status = BodyLabel(text="Выключен", color=COLORS["text_muted"], font_size=sp(10.5), size_hint_y=None)
        voice_text_col.add_widget(self.voice_status)
        self.voice_card.add_widget(voice_text_col)
        self.voice_card.add_widget(Widget())
        self.mic_button = VoiceMicButton()
        self.mic_button.bind(on_release=self._toggle_mic)
        self.voice_card.add_widget(self.mic_button)
        content.add_widget(self.voice_card)

        self.chat_card = RoundedPanel(
            orientation="vertical",
            size_hint_y=1,
            spacing=dp(8),
            padding=[dp(14), dp(12), dp(14), dp(12)],
        )
        self.chat_card.add_widget(PixelLabel(text="Текстовый чат", center=True, font_size=sp(13), size_hint_y=None))

        self.chat_scroll = ScrollView(do_scroll_x=False, bar_width=dp(4), scroll_type=["bars", "content"])
        self.chat_box = BoxLayout(orientation="vertical", spacing=dp(6), size_hint_y=None)
        self.chat_box.bind(minimum_height=self.chat_box.setter("height"))
        self.chat_scroll.add_widget(self.chat_box)
        self.chat_card.add_widget(self.chat_scroll)

        self.chat_input_row = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(48))
        self.chat_input = AppTextInput(hint_text="Пиши догадку в чат...", height=dp(46))
        self.chat_input_row.add_widget(self.chat_input)
        self.send_btn = AppButton(text="Отправить", compact=True, font_size=sp(13), size_hint=(None, None), size=(dp(130), dp(46)))
        self.send_btn.bind(on_release=self._send_chat_message)
        self.chat_input_row.add_widget(self.send_btn)
        self.chat_card.add_widget(self.chat_input_row)

        self.status_label = BodyLabel(
            center=True,
            color=COLORS["text_muted"],
            font_size=sp(11),
            size_hint_y=None,
            text="Объясняющий запускает игру, затем объясняет слова голосом.",
        )
        self.chat_card.add_widget(self.status_label)
        content.add_widget(self.chat_card)

        self.countdown_overlay = FullscreenCountdownOverlay()

        root.add_widget(content)
        root.add_widget(self.countdown_overlay)
        self.add_widget(root)

    def _start_button_hit(self, touch):
        return (
            self.manager is not None
            and self.manager.current == self.name
            and self._current_phase() == "lobby"
            and self._can_control_start()
            and not self.start_game_btn.disabled
            and self.start_game_btn.opacity > 0
            and self.start_game_btn.collide_point(*touch.pos)
        )

    def on_touch_down(self, touch):
        if self._start_button_hit(touch):
            self._queue_start_game()
            return True
        return super().on_touch_down(touch)

    def on_pre_enter(self, *_):
        self.disabled = False
        app = App.get_running_app()
        room_data = app.get_active_room() if app is not None else {}
        self.room_code = (room_data or {}).get("code", "")
        player_name = self._player_name()
        self._last_voice_ping_ts = 0.0
        self._smoothed_voice_level = 0.0
        self._last_chat_signature = None
        self._leave_sent = False
        self._last_start_attempt_ts = 0.0
        self._start_game_request_in_flight = False
        self.mic_button.set_muted(True)
        self.mic_button.set_level(0.0)
        self.mic_button_top.set_muted(True)
        self.mic_button_top.set_level(0.0)
        self.coin_badge.refresh_from_session()
        self.countdown_overlay.hide()
        if self.room_code and player_name:
            try:
                joined_room = join_online_room(room_code=self.room_code, player_name=player_name)
                if app is not None:
                    app.set_active_room(joined_room)
            except (ConnectionError, ValueError):
                pass
        self._start_polling()
        self._start_voice_ui_sync()
        self._start_voice_engine()
        self._poll_state()

    def on_leave(self, *_):
        self._stop_polling()
        self._stop_voice_ui_sync()
        self._stop_voice_engine()
        self.countdown_overlay.hide()
        self._dismiss_leave_popup()
        self.disabled = True

    def _go_back_to_menu(self, *_):
        if self._current_phase() in {"countdown", "round"}:
            self._open_leave_popup()
            return
        self._leave_room()
        self.manager.current = "start"

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

    def _sync_word_stage_layout(self, *_):
        card_width = max(dp(220), self.word_stage.width - dp(12))
        self.word_card.size = (card_width, self.word_card_height)
        self._reset_word_card_position()

    def _reset_word_card_position(self):
        self.word_card.pos = (
            self.word_stage.x + (self.word_stage.width - self.word_card.width) / 2,
            self.word_stage.y + (self.word_stage.height - self.word_card.height) / 2,
        )
        self.word_card.opacity = 1.0

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

    def _player_name(self):
        app = App.get_running_app()
        return app.resolve_player_name() if app is not None else None

    def _normalized_player_name(self, value):
        return (value or "").strip().lower()

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

    def _is_explainer(self):
        viewer = self._viewer_state()
        if viewer:
            return bool(viewer.get("is_explainer"))
        room = self.room_state.get("room", {})
        return self._same_player(self._player_name(), room.get("current_explainer"))

    def _is_host(self):
        room = self.room_state.get("room", {})
        return self._same_player(self._player_name(), room.get("host_name"))

    def _can_control_start(self):
        viewer = self._viewer_state()
        if viewer and "can_control_start" in viewer:
            return bool(viewer.get("can_control_start"))
        return bool(self._player_name()) and self._is_explainer() and self._current_phase() == "lobby"

    def _can_start_game(self):
        viewer = self._viewer_state()
        if viewer:
            return bool(viewer.get("can_start_game"))
        return bool(self._player_name()) and self._is_explainer()

    def _explainer_chat_locked(self):
        return self._is_explainer() and self._current_phase() in {"countdown", "round"}

    def _can_send_chat(self):
        if self._explainer_chat_locked():
            return False
        viewer = self._viewer_state()
        if viewer:
            return bool(viewer.get("can_send_chat"))
        return bool(self._player_name())

    def _can_use_voice(self):
        viewer = self._viewer_state()
        if viewer:
            return bool(viewer.get("can_use_voice"))
        return self._is_explainer() and self._current_phase() == "round"

    def _can_toggle_mic(self):
        return self._can_use_voice() and self.voice_engine.available

    def _required_players_to_start(self, room):
        return 1

    def _profile_map(self):
        try:
            return {profile.name.strip().lower(): profile for profile in list_profiles()}
        except Exception:
            return {}

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
            should_transmit=lambda: self._can_use_voice() and not self.mic_button.muted,
        )
        self.voice_engine.set_muted(self.mic_button.muted)

    def _stop_voice_engine(self):
        self.voice_engine.stop()
        self._smoothed_voice_level = 0.0

    def _set_button_visibility(self, button, visible):
        button.disabled = not visible
        button.opacity = 1 if visible else 0

    def _set_panel_visibility(self, panel, visible, shown_height):
        panel.disabled = not visible
        panel.opacity = 1 if visible else 0
        panel.height = shown_height if visible else dp(0)

    def _show_explainer_controls(self, is_explainer, phase):
        self._set_button_visibility(self.start_game_btn, phase == "lobby" and self._can_control_start())

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

    def _render_player_cards(self, players, explainer_name, profile_map=None, score_map=None, phase="lobby"):
        self.players_box.clear_widgets()
        is_round = phase == "round"
        self.players_box.cols = 1 if is_round or not players else 3
        self.players_box.row_default_height = dp(44) if is_round else dp(102)
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

        profile_map = profile_map or self._profile_map()
        score_map = score_map or {}
        current_player_name = self._player_name()

        for listed_player in players:
            card = RoundPlayerRow() if is_round else LobbyPlayerCard()
            card.width = self.players_box.col_default_width
            profile = profile_map.get((listed_player or "").strip().lower())
            card.set_player(
                listed_player,
                profile,
                is_explainer=self._same_player(listed_player, explainer_name),
                is_self=self._same_player(listed_player, current_player_name),
                room_score=score_map.get((listed_player or "").strip().lower(), 0),
                phase=phase,
            )
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
            message = str(error)
            if "Player is not in this room." in message:
                app = App.get_running_app()
                if app is not None:
                    app.clear_active_room()
                self.room_code = ""
                self.room_state = {}
                self.status_label.color = COLORS["warning"]
                self.status_label.text = "Ты больше не в этой комнате. Зайди в нее заново."
                Clock.schedule_once(lambda *_: setattr(self.manager, "current", "join_room"), 0)
                return
            self.status_label.color = COLORS["warning"]
            self.status_label.text = message
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
        viewer = self._viewer_state()

        player_name = self._player_name() or ""
        is_explainer = bool(viewer.get("is_explainer")) if viewer else self._same_player(player_name, room.get("current_explainer"))
        phase = self._current_phase()
        self._set_room_exit_button(phase in {"countdown", "round"})
        countdown_left = int(self.room_state.get("countdown_left_sec") or 0)
        round_left = int(self.room_state.get("round_left_sec") or 0)
        explainer_name = room.get("current_explainer") or "—"

        room_name = room.get("room_name", "Комната")
        code = room.get("code", self.room_code)
        players_count = int(room.get("players_count") or len(players) or 0)
        max_players = int(room.get("max_players") or max(players_count, 1))
        players_text = f"{players_count}/{max_players}"
        profile_map = self._profile_map()
        score_map = {
            (score_entry.get("player_name") or "").strip().lower(): int(score_entry.get("score") or 0)
            for score_entry in scores
        }
        explainer_profile = profile_map.get((explainer_name or "").strip().lower())

        self.room_meta_label.text = f"{room_name} | Код: {code} | Игроков: {players_text}"
        if phase == "round":
            self.players_wrap_title.text = f"Игроки и очки • {players_text}"
        else:
            self.players_wrap_title.text = f"Игроки в комнате • {players_text}"
        self.players_label.text = f"Игроков: {players_text}"

        if phase == "round":
            self.players_wrap_title.text = f"Игроки • {players_text}"

        explainer_can_only_voice = is_explainer and phase == "round"
        explainer_chat_locked = self._explainer_chat_locked()
        explainer_round = explainer_can_only_voice

        self.brand_title.height = dp(0) if explainer_round else self.brand_title_height
        self.brand_title.opacity = 0 if explainer_round else 1
        if explainer_round:
            self.chat_card._bg_color.rgba = (0.05, 0.09, 0.15, 0.34)
            self.chat_card._border_color.rgba = (1, 1, 1, 0.08)
            self.chat_card._shadow_color.rgba = (0, 0, 0, 0.08)
        else:
            self.chat_card._bg_color.rgba = COLORS["surface"]
            self.chat_card._border_color.rgba = COLORS["outline"]
            self.chat_card._shadow_color.rgba = (0, 0, 0, 0.24)

        can_chat = self._can_send_chat()
        if explainer_can_only_voice:
            self._set_word_text(self.room_state.get("current_word"))
            self.chat_input.hint_text = "Объясняющий не пишет в чат."
            self.mic_button.set_enabled(self._can_toggle_mic())
            self.mic_button_top.set_enabled(self._can_toggle_mic())
        else:
            self._set_word_text("Слово скрыто")
            if explainer_chat_locked:
                self.chat_input.hint_text = "Объясняющий не пишет в чат."
            else:
                self.chat_input.hint_text = "Пиши догадку в чат..." if phase == "round" else "Сообщение в чат..."
            self.mic_button.set_enabled(False)
            self.mic_button.set_muted(True)
            self.mic_button_top.set_enabled(False)
            self.mic_button_top.set_muted(True)
            self.voice_engine.set_muted(True)
        self._set_chat_input_visibility(can_chat)

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
        self.explainer_card.set_explainer(explainer_name, explainer_profile, mic_state_text)
        if not self.voice_engine.available:
            self.voice_status.text = "Голос недоступен на этом устройстве."
        elif self.mic_button.muted:
            self.voice_status.text = "Выключен"
        elif voice_active and voice_speaker == explainer_name:
            self.voice_status.text = "Говоришь"
        else:
            self.voice_status.text = "Включен"
        if phase == "lobby":
            self.explainer_status_label.text = f"Объясняет слова: {explainer_name}"
        else:
            self.explainer_status_label.text = f"Объясняет слова: {explainer_name} | Микрофон: {mic_state_text}"

        self._show_explainer_controls(is_explainer, phase)
        show_players_grid = phase in {"lobby", "round"}
        players_panel_height = self.players_wrap_round_height if phase == "round" else self.players_wrap_height
        self._set_panel_visibility(self.room_meta_wrap, phase != "lobby" and not is_explainer, self.room_meta_wrap_height)
        self._set_panel_visibility(self.players_wrap, show_players_grid, players_panel_height)
        self._set_panel_visibility(self.players_summary_wrap, phase == "round" and is_explainer, self.players_summary_wrap_height)
        self._set_panel_visibility(
            self.lobby_start_row,
            phase == "lobby" and self._can_control_start(),
            self.lobby_start_height,
        )
        self._set_panel_visibility(self.explainer_card, phase in {"countdown", "round"} and not is_explainer, self.explainer_card_height)
        self._set_panel_visibility(self.word_stage, phase == "round" and is_explainer, self.word_stage_height)
        self._set_panel_visibility(self.voice_card, False, self.voice_card_height)
        self._set_panel_visibility(self.scores_wrap, phase == "round" and is_explainer, self.scores_wrap_height)
        self._set_panel_visibility(self.phase_wrap, phase in {"countdown", "round"}, self.phase_wrap_height)

        if phase == "lobby":
            self.phase_label.text = ""
            self.countdown_overlay.hide()
            self.status_label.color = COLORS["text_muted"]
            if self._is_explainer():
                self.status_label.text = "Нажми \"Начать игру\", когда все готовы."
            else:
                self.status_label.text = "Ждите объясняющего. Он запустит игру, когда будет готов."
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
                self.status_label.text = "Свайпни карточку вверх или вниз, чтобы скипнуть слово."
            else:
                self.status_label.color = COLORS["text_muted"]
                self.status_label.text = "Пиши догадки в чат. За верное слово ты тоже получаешь +1."

        self._render_player_cards(players, explainer_name, profile_map, score_map, phase)
        if phase == "round" and is_explainer:
            self._sync_word_stage_layout()

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

    def _queue_start_game(self, *_):
        now_ts = time.time()
        if self._start_game_request_in_flight or now_ts - self._last_start_attempt_ts < 0.35:
            return
        self._last_start_attempt_ts = now_ts
        self._start_game()

    def _start_game(self, *_):
        player_name = self._player_name()
        if player_name and self.room_code:
            self._start_game_request_in_flight = True
            self.start_game_btn.disabled = True

            try:
                start_response = start_room_game(room_code=self.room_code, player_name=player_name)
            except ConnectionError as error:
                self.status_label.color = COLORS["error"]
                self.status_label.text = str(error)
                self._start_game_request_in_flight = False
                self.start_game_btn.disabled = False
                return
            except ValueError as error:
                self.status_label.color = COLORS["warning"]
                self.status_label.text = str(error)
                self._start_game_request_in_flight = False
                self.start_game_btn.disabled = False
                return

            if isinstance(start_response, dict):
                updated_state = dict(self.room_state or {})
                for key in (
                    "room",
                    "players",
                    "scores",
                    "messages",
                    "viewer",
                    "voice_active",
                    "voice_speaker",
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
                self.room_state = updated_state
                self._apply_state()

            self._start_game_request_in_flight = False
            self.status_label.color = COLORS["success"]
            self.status_label.text = "РЎС‚Р°СЂС‚ РёРіСЂС‹! РќР° СЌРєСЂР°РЅРµ РѕР±С‰РёР№ РѕС‚СЃС‡РµС‚ 10 СЃРµРєСѓРЅРґ."
            self._poll_state()
            return
        if self._current_phase() != "lobby":
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Игра уже запущена."
            return

        if not self._is_explainer():
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Начать игру может только тот, кто объясняет слова."
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
            for key in (
                "room",
                "players",
                "scores",
                "messages",
                "viewer",
                "voice_active",
                "voice_speaker",
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
            self.room_state = updated_state
            self._apply_state()

        self.status_label.color = COLORS["success"]
        self.status_label.text = "Старт игры! На экране общий отсчет 10 секунд."
        self._poll_state()

    def _send_chat_message(self, *_):
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
        try:
            if phase == "round":
                result = send_room_guess(room_code=self.room_code, player_name=player_name, guess=text)
                if result.get("correct"):
                    awarded_player = result.get("awarded_player") or "объясняющий"
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
            self.status_label.text = "Скипать слова может только объясняющий."
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
        if isinstance(response, dict):
            updated_state = dict(self.room_state or {})
            if "room" in response:
                updated_state["room"] = response.get("room") or {}
            if "scores" in response:
                updated_state["scores"] = response.get("scores") or []
            if "current_word" in response:
                updated_state["current_word"] = response.get("current_word") or ""
            updated_state["game_phase"] = "round"
            self.room_state = updated_state
            self.word_card.opacity = 1.0
            self._apply_state()
        Clock.schedule_once(lambda *_: self._poll_state(), 0.1)

    def _toggle_mic(self, *_):
        if not self._can_use_voice():
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Микрофон доступен только тому, кто объясняет слова."
            return
        if not self.voice_engine.available:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "На этом устройстве голосовой микрофон недоступен."
            return

        new_muted = not self.mic_button.muted
        self.mic_button.set_muted(new_muted)
        self.mic_button_top.set_muted(new_muted)
        self.voice_engine.set_muted(new_muted)
        if new_muted:
            self.voice_status.text = "Микрофон выключен"
            self.status_label.color = COLORS["text_muted"]
            self.status_label.text = "Микрофон выключен."
        else:
            self.voice_status.text = "Микрофон включен"
            self.status_label.color = COLORS["success"]
            self.status_label.text = "Микрофон включен."

    def _sync_voice_ui(self):
        if not self._can_use_voice():
            self._smoothed_voice_level = 0.0
            self.mic_button.set_level(0.0)
            self.mic_button_top.set_level(0.0)
            return
        if not self.voice_engine.available:
            self._smoothed_voice_level = 0.0
            self.mic_button.set_level(0.0)
            self.mic_button_top.set_level(0.0)
            return

        raw_level = self.voice_engine.level() if self.voice_engine.active() else 0.0
        if self.mic_button.muted:
            raw_level = 0.0

        smoothing = 0.38 if raw_level >= self._smoothed_voice_level else 0.20
        self._smoothed_voice_level += (raw_level - self._smoothed_voice_level) * smoothing
        if self._smoothed_voice_level < 0.015:
            self._smoothed_voice_level = 0.0

        self.mic_button.set_level(self._smoothed_voice_level)
        self.mic_button_top.set_level(self._smoothed_voice_level)

        if not self._can_use_voice() or self.mic_button.muted:
            return

        if raw_level < 0.06:
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
