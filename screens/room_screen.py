import time
from pathlib import Path
from threading import Thread
from types import SimpleNamespace

from kivy.app import App
from kivy.animation import Animation
from kivy.clock import Clock
from kivy.graphics import (
    Color,
    Ellipse,
    Line,
    Rectangle,
    RoundedRectangle,
)
from kivy.core.image import Image as CoreImage
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
    ROOM_CREATION_COST,
    RoomVoiceEngine,
    get_online_room_state,
    join_online_room,
    leave_online_room,
    list_profiles,
    ping_room_voice,
    send_room_chat,
    send_room_guess,
    set_room_mic_state,
    skip_room_word,
    spend_alias_coins,
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
    LoadingOverlay,
    PixelLabel,
    RoundedPanel,
    ScreenBackground,
    register_game_font,
)


MIC_ICON_PATH = Path(__file__).resolve().parents[1] / "image" / "mic_white.png"


class VoiceMicButton(ButtonBehavior, Widget):
    _mic_texture_cache = None
    _mic_texture_ready = False

    @classmethod
    def _mic_texture(cls):
        if cls._mic_texture_ready:
            return cls._mic_texture_cache

        cls._mic_texture_ready = True
        try:
            cls._mic_texture_cache = CoreImage(str(MIC_ICON_PATH)).texture
        except Exception:
            cls._mic_texture_cache = None
        return cls._mic_texture_cache

    def __init__(self, **kwargs):
        button_size = kwargs.pop("size", (dp(84), dp(84)))
        button_size_hint = kwargs.pop("size_hint", (None, None))
        super().__init__(size_hint=button_size_hint, size=button_size, **kwargs)
        self._muted = True
        self._enabled = True
        self._level = 0.0
        self._hit_padding = dp(32)
        self._pressed_touch = None
        self._texture = self._mic_texture()

        with self.canvas.before:
            self._shadow_color = Color(0, 0, 0, 0.22)
            self._shadow = Ellipse(pos=self.pos, size=self.size)
            self._bg_color = Color(0.08, 0.13, 0.21, 0.98)
            self._bg = Ellipse(pos=self.pos, size=self.size)
            self._halo_color = Color(0.22, 0.90, 0.42, 0.0)
            self._halo = Ellipse(pos=self.pos, size=self.size)
            self._ring_color = Color(1, 1, 1, 0.15)
            self._ring = Line(width=1.4, ellipse=(self.x, self.y, self.width, self.height))
            self._outline_color = Color(1, 1, 1, 0.18)
            self._outline = Line(width=1.2, ellipse=(self.x, self.y, self.width, self.height))

        with self.canvas:
            self._icon_color = Color(0.98, 0.99, 1.0, 1.0)
            self._icon_base = Rectangle(pos=self.pos, size=(0, 0), texture=self._texture)
            self._fill_color = Color(0.22, 0.92, 0.40, 0.0)
            self._icon_fill = Rectangle(pos=self.pos, size=(0, 0), texture=self._texture)
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

    def collide_point(self, x, y):
        return (
            self.x - self._hit_padding <= x <= self.right + self._hit_padding
            and self.y - self._hit_padding <= y <= self.top + self._hit_padding
        )

    def on_touch_down(self, touch):
        if getattr(touch, "is_mouse_scrolling", False):
            return super().on_touch_down(touch)
        if self.disabled:
            return super().on_touch_down(touch)
        if not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        touch.grab(self)
        self._pressed_touch = touch
        self.dispatch("on_press")
        return True

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            was_inside = self.collide_point(*touch.pos)
            self._pressed_touch = None
            if was_inside:
                self.dispatch("on_release")
            else:
                self._refresh_state()
            return True
        return super().on_touch_up(touch)

    def on_press(self):
        self._bg_color.rgba = (0.05, 0.09, 0.16, 0.98)

    def on_release(self):
        self._refresh_state()

    def _refresh_state(self):
        if not self._enabled:
            self._bg_color.rgba = (0.14, 0.14, 0.16, 0.82)
            self._icon_color.rgba = (0.72, 0.75, 0.80, 0.92)
            self._fill_color.rgba = (0.22, 0.90, 0.42, 0.0)
            self._outline_color.rgba = (1, 1, 1, 0.08)
            self._ring_color.rgba = (1, 1, 1, 0.08)
            self._halo_color.rgba = (0.22, 0.90, 0.42, 0.0)
            self._mute_color.rgba = (0.96, 0.23, 0.23, 0.0)
        else:
            if self._muted:
                self._bg_color.rgba = (0.08, 0.13, 0.21, 0.98)
                self._icon_color.rgba = (0.98, 0.99, 1.0, 1.0)
                self._fill_color.rgba = (0.22, 0.90, 0.42, 0.0)
                self._outline_color.rgba = (1, 1, 1, 0.16)
                self._ring_color.rgba = (1, 1, 1, 0.14)
                self._halo_color.rgba = (0.22, 0.90, 0.42, 0.0)
            else:
                level = self._level
                glow_alpha = 0.16 + level * 0.34
                self._bg_color.rgba = (0.08, 0.13, 0.21, 0.98)
                self._icon_color.rgba = (0.98, 0.99, 1.0, 1.0)
                self._fill_color.rgba = (0.22, 0.92, 0.40, 0.96)
                self._outline_color.rgba = (0.44, 0.94, 0.58, glow_alpha)
                self._ring_color.rgba = (0.64, 0.98, 0.74, 0.16 + level * 0.26)
                self._halo_color.rgba = (0.22, 0.90, 0.42, 0.07 + level * 0.18)
            self._mute_color.rgba = (0.96, 0.23, 0.23, 0.95 if self._muted else 0.0)

        self._sync_canvas()

    def _sync_canvas(self, *_):
        self._shadow.pos = (self.x, self.y - dp(1.5))
        self._shadow.size = self.size
        halo_inset = dp(3.5)
        self._halo.pos = (self.x + halo_inset, self.y + halo_inset)
        self._halo.size = (max(0, self.width - halo_inset * 2), max(0, self.height - halo_inset * 2))
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._outline.ellipse = (self.x, self.y, self.width, self.height)
        self._ring.ellipse = (self.x + dp(1.4), self.y + dp(1.4), self.width - dp(2.8), self.height - dp(2.8))

        icon_size = min(self.width, self.height) * 0.60
        icon_x = self.center_x - icon_size / 2
        icon_y = self.center_y - icon_size / 2 + dp(0.5)
        self._icon_base.texture = self._texture
        self._icon_base.pos = (icon_x, icon_y)
        self._icon_base.size = (icon_size, icon_size)
        self._icon_base.tex_coords = (0, 0, 1, 0, 1, 1, 0, 1)

        fill_level = 0.0
        if self._enabled and not self._muted:
            fill_level = max(0.0, min(1.0, self._level))
            fill_level = fill_level ** 0.88

        if fill_level <= 0.001 or self._texture is None:
            self._icon_fill.size = (0, 0)
        else:
            fill_h = max(dp(1), icon_size * fill_level)
            fill_top_v = max(0.0, min(1.0, fill_level))
            self._icon_fill.texture = self._texture
            self._icon_fill.pos = (icon_x, icon_y)
            self._icon_fill.size = (icon_size, fill_h)
            self._icon_fill.tex_coords = (0, 0, 1, 0, 1, fill_top_v, 0, fill_top_v)

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
        self._drag_axis = None
        super().__init__(**kwargs)

    def set_swipe_callback(self, callback):
        self._swipe_callback = callback

    def on_touch_down(self, touch):
        if getattr(self, "disabled", False) or not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        Animation.cancel_all(self)
        self._swipe_start = touch.pos
        self._home_pos = self.pos
        self._drag_axis = None
        touch.grab(self)
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is not self or self._home_pos is None or self._animating:
            return super().on_touch_move(touch)

        delta_x = touch.x - self._swipe_start[0]
        delta_y = touch.y - self._swipe_start[1]
        if self._drag_axis is None and max(abs(delta_x), abs(delta_y)) >= dp(8):
            self._drag_axis = "horizontal" if abs(delta_x) > abs(delta_y) else "vertical"

        if self._drag_axis == "horizontal":
            self.x = self._home_pos[0] + delta_x * 0.56
            self.y = self._home_pos[1] + delta_y * 0.12
            fade = min(0.58, abs(delta_x) / max(dp(1), self.width * 1.05))
            self.opacity = 1.0 - fade
        else:
            self.y = self._home_pos[1] + delta_y * 0.46
            self.x = self._home_pos[0] + delta_x * 0.10
            fade = min(0.58, abs(delta_y) / max(dp(1), self.height * 1.05))
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
        if abs(delta_x) >= self._swipe_threshold and abs(delta_x) > abs(delta_y):
            self.animate_swipe_out("right" if delta_x > 0 else "left", callback=self._swipe_callback)
        elif abs(delta_y) >= self._swipe_threshold and abs(delta_y) >= abs(delta_x):
            self.animate_swipe_out("up" if delta_y > 0 else "down", callback=self._swipe_callback)
        else:
            self.animate_back_home()
        return True

    def animate_back_home(self):
        if self._home_pos is None:
            return
        Animation.cancel_all(self)
        Animation(x=self._home_pos[0], y=self._home_pos[1], opacity=1.0, d=0.12, t="out_quad").start(self)

    def animate_swipe_out(self, direction, callback=None):
        if self._home_pos is None or self._animating:
            return

        self._animating = True
        home_x, home_y = self._home_pos
        target_x = home_x
        target_y = home_y
        if direction == "up":
            target_y = home_y + self.height * 1.75
        elif direction == "down":
            target_y = home_y - self.height * 1.75
        elif direction == "right":
            target_x = home_x + self.width * 1.85
        else:
            target_x = home_x - self.width * 1.85

        Animation.cancel_all(self)
        animation = Animation(x=target_x, y=target_y, opacity=0.0, d=0.16, t="out_quad")

        def _finish(*_):
            self.pos = (home_x, home_y)
            self.opacity = 1.0
            self._animating = False
            self._drag_axis = None
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
            spacing=dp(5),
            padding=[dp(8), dp(8), dp(8), dp(8)],
            size_hint_x=None,
            size_hint_y=None,
            height=dp(126),
            bg_color=(0.10, 0.15, 0.24, 0.98),
            shadow_alpha=0.16,
            **kwargs,
        )
        self.role_label = Label(
            text="",
            font_name="GameFont",
            font_size=sp(8.2),
            color=COLORS["accent"],
            halign="center",
            valign="middle",
            size_hint_y=None,
            height=dp(14),
            opacity=0,
        )
        self.role_label.bind(size=lambda *_: setattr(self.role_label, "text_size", self.role_label.size))
        self.add_widget(self.role_label)

        self.name_label = PixelLabel(
            text="",
            center=True,
            font_size=sp(11.5),
            size_hint_y=None,
            shorten=True,
            shorten_from="right",
            max_lines=1,
        )

        avatar_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(42))
        avatar_row.add_widget(Widget())
        self.avatar = AvatarButton()
        self.avatar.size = (dp(42), dp(42))
        self.avatar.disabled = True
        avatar_row.add_widget(self.avatar)
        avatar_row.add_widget(Widget())
        self.add_widget(avatar_row)
        self.add_widget(self.name_label)

        text_col = BoxLayout(orientation="vertical", spacing=dp(3), size_hint_y=None, height=dp(42))
        self.games_label = BodyLabel(text="", center=True, color=COLORS["text_soft"], font_size=sp(8.5), size_hint_y=None)
        text_col.add_widget(self.games_label)
        self.earned_label = BodyLabel(text="", center=True, color=COLORS["accent"], font_size=sp(8.5), size_hint_y=None)
        text_col.add_widget(self.earned_label)
        self.add_widget(text_col)

    def set_player(self, player_name, profile, is_explainer=False, is_self=False, is_host=False, room_score=0, phase="lobby"):
        self.avatar.set_profile(profile)
        games_played = getattr(profile, "games_played", 0) if profile is not None else 0
        total_earned = getattr(profile, "total_points", 0) if profile is not None else 0
        display_name = player_name or "Игрок"
        role_tags = []
        if is_host:
            role_tags.append("ХОСТ")
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

    def set_player(self, player_name, profile, room_score=0, is_explainer=False, is_self=False, is_host=False, phase="round"):
        self.avatar.set_profile(profile)
        badges = []
        if is_host:
            badges.append("ХОСТ")
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


class ClickableLobbyPlayerCard(ButtonBehavior, LobbyPlayerCard):
    def on_press(self):
        self.opacity = 0.88

    def on_release(self):
        self.opacity = 1


class ClickableRoundPlayerRow(ButtonBehavior, RoundPlayerRow):
    def on_press(self):
        self.opacity = 0.88

    def on_release(self):
        self.opacity = 1


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
            self._ring_color = Color(*COLORS["accent"])
            self._ring = Line(width=dp(2.8), circle=(0, 0, 0))
            self._inner_color = Color(0.06, 0.10, 0.18, 0.92)
            self._inner = Ellipse(pos=(0, 0), size=(0, 0))

        self._label = Label(
            text="",
            font_name="BrandFont",
            font_size=sp(132),
            color=(1, 1, 1, 1),
            halign="center",
            valign="middle",
        )
        self.add_widget(self._label)
        self._caption = Label(
            text="СТАРТ ЧЕРЕЗ",
            font_name="GameFont",
            font_size=sp(18),
            color=COLORS["accent"],
            halign="center",
            valign="middle",
            size_hint=(None, None),
            size=(dp(220), dp(34)),
        )
        self.add_widget(self._caption)
        self.bind(pos=self._sync_canvas, size=self._sync_canvas)
        self.hide()

    def _sync_canvas(self, *_):
        self._shade_rect.pos = self.pos
        self._shade_rect.size = self.size
        diameter = min(self.width, self.height) * 0.46
        cx, cy = self.center_x, self.center_y + dp(18)
        self._inner.pos = (cx - diameter / 2, cy - diameter / 2)
        self._inner.size = (diameter, diameter)
        self._ring.circle = (cx, cy, diameter / 2)
        self._label.pos = self.pos
        self._label.size = self.size
        self._label.text_size = self.size
        self._caption.pos = (self.center_x - self._caption.width / 2, cy + diameter / 2 + dp(8))
        self._caption.text_size = self._caption.size

    def show(self, seconds_left):
        self._active = True
        self.opacity = 1
        number = max(1, int(seconds_left))
        self._label.text = str(number)
        self._caption.text = "СТАРТ ЧЕРЕЗ"
        self._sync_canvas()

    def hide(self):
        self._active = False
        self.opacity = 0
        self._label.text = ""

    def on_touch_down(self, touch):
        return False

    def on_touch_move(self, touch):
        return False

    def on_touch_up(self, touch):
        return False


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
        self._mic_muted_state = True
        self._start_game_scheduled = False
        self._last_start_attempt_ts = 0.0
        self._start_game_request_in_flight = False
        self._local_starts_count = 0
        self._last_players_signature = None
        self._last_chat_mount_signature = None
        self._last_progress_signature = None
        self._last_overlay_geometry_signature = None
        self._profile_cache = {}
        self._profile_cache_ts = 0.0
        self._poll_in_flight = False
        self._poll_token = 0
        self._poll_reschedule = False
        self._chat_request_in_flight = False
        self._skip_request_in_flight = False
        self._chat_request_token = 0
        self._skip_request_token = 0
        self._message_history = []
        self._last_message_id = 0

        root = ScreenBackground(variant="game")
        content = BoxLayout(
            orientation="vertical",
            padding=[dp(8), dp(10), dp(8), dp(10)],
            spacing=dp(6),
        )

        top_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(56))
        self.back_btn = AppButton(text="В меню", compact=True, size_hint=(None, None), size=(dp(122), dp(46)))
        self.back_btn.bind(on_release=self._go_back_to_menu)
        self._set_room_exit_button(False)
        top_row.add_widget(self.back_btn)
        top_row.add_widget(Widget())
        self.coin_badge = CoinBadge(size=(dp(116), dp(46)))
        top_row.add_widget(self.coin_badge)
        content.add_widget(top_row)

        self.room_meta_wrap_height = dp(18)
        self.room_meta_wrap = BoxLayout(orientation="horizontal", size_hint_y=None, height=self.room_meta_wrap_height)
        self.room_meta_label = BodyLabel(center=True, color=COLORS["text_muted"], font_size=sp(11), size_hint_y=None, text="")
        self.room_meta_wrap.add_widget(self.room_meta_label)
        content.add_widget(self.room_meta_wrap)
        self.brand_title_height = dp(72)
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

        self.players_wrap_height = dp(248)
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
            spacing=dp(8),
            padding=[dp(4), dp(4), dp(4), dp(4)],
            size_hint=(None, None),
            row_default_height=dp(126),
            row_force_default=True,
            col_default_width=dp(108),
            col_force_default=True,
        )
        self.players_box.bind(minimum_height=self.players_box.setter("height"))
        self.players_scroll.bind(width=self._sync_players_grid_width)
        self.players_scroll.add_widget(self.players_box)
        self.players_wrap.add_widget(self.players_scroll)
        content.add_widget(self.players_wrap)

        self.scores_wrap_height = dp(132)
        self.scores_wrap_overlay_height = dp(162)
        self.scores_wrap = FloatLayout(size_hint_y=None, height=self.scores_wrap_height)
        self.score_chat_layer = FloatLayout(size_hint=(1, 1), opacity=0, disabled=True)
        self.scores_wrap.add_widget(self.score_chat_layer)
        self.score_badge = ScoreBadge(pos_hint={"center_x": 0.5, "top": 1.0})
        self.scores_wrap.add_widget(self.score_badge)
        self.mic_button_top = VoiceMicButton(size=(dp(88), dp(88)), pos_hint={"right": 0.98, "top": 0.96})
        self.mic_button_top.bind(on_release=self._toggle_mic)
        self.mic_button_top.opacity = 0
        self.mic_button_top.disabled = True
        self.scores_wrap.add_widget(self.mic_button_top)
        content.add_widget(self.scores_wrap)

        self.players_summary_wrap_height = dp(22)
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
        self.start_game_btn.bind(on_release=self._queue_start_game)
        self.lobby_start_row.add_widget(self.start_game_btn)
        self.wait_host_btn = AppButton(
            text="Ожидание старта от хоста",
            compact=True,
            font_size=sp(13),
            size_hint=(None, None),
            size=(dp(228), dp(46)),
        )
        self.wait_host_btn.disabled = True
        self.wait_host_btn.opacity = 0
        self.lobby_start_row.add_widget(self.wait_host_btn)
        self.lobby_start_row.add_widget(Widget())
        content.add_widget(self.lobby_start_row)

        self.phase_wrap_height = dp(62)
        self.phase_wrap = RoundedPanel(
            orientation="horizontal",
            size_hint_y=None,
            height=self.phase_wrap_height,
            padding=[dp(12), dp(8), dp(12), dp(8)],
            bg_color=(0.08, 0.13, 0.21, 0.94),
            shadow_alpha=0.16,
        )
        self.phase_wrap._border_color.rgba = COLORS["accent"]
        self.phase_wrap._border_line.width = 1.5
        self.phase_label = PixelLabel(center=True, color=COLORS["warning"], font_size=sp(23), size_hint_y=None, text="")
        self.phase_wrap.add_widget(self.phase_label)
        content.add_widget(self.phase_wrap)

        self.explainer_card_height = dp(138)
        self.explainer_card = ExplainerSpotlightCard()
        self.explainer_card.height = self.explainer_card_height
        content.add_widget(self.explainer_card)

        self.word_push_spacer = Widget(size_hint_y=None, height=dp(0))
        content.add_widget(self.word_push_spacer)

        self.word_card_height = dp(188)
        self.word_stage_height = dp(198)
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

        self.voice_card_height = dp(0)
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

        self.chat_host = BoxLayout(orientation="vertical", size_hint_y=1)

        self.chat_card = RoundedPanel(
            orientation="vertical",
            size_hint_y=1,
            spacing=dp(6),
            padding=[dp(12), dp(8), dp(12), dp(8)],
        )
        self.chat_title = PixelLabel(text="Текстовый чат", center=True, font_size=sp(13), size_hint_y=None)
        self.chat_card.add_widget(self.chat_title)

        self.chat_scroll = ScrollView(do_scroll_x=False, bar_width=dp(4), scroll_type=["bars", "content"])
        self.chat_box = BoxLayout(orientation="vertical", spacing=dp(2), size_hint_y=None)
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
            auto_height=False,
            text="Объясняющий запускает игру, затем объясняет слова голосом.",
        )
        self.status_label.height = dp(0)
        self.status_label.opacity = 0
        self.status_label.disabled = True
        self.chat_card.add_widget(self.status_label)
        self.chat_host.add_widget(self.chat_card)
        content.add_widget(self.chat_host)

        self.countdown_overlay = FullscreenCountdownOverlay()
        self.chat_overlay_layer = FloatLayout(size_hint=(1, 1), opacity=0, disabled=True)

        root.add_widget(content)
        root.add_widget(self.chat_overlay_layer)
        root.add_widget(self.countdown_overlay)
        self.loading_overlay = LoadingOverlay()
        root.add_widget(self.loading_overlay)
        self.add_widget(root)

    def on_pre_enter(self, *_):
        self.disabled = False
        app = App.get_running_app()
        room_data = app.get_active_room() if app is not None else {}
        self.room_code = (room_data or {}).get("code", "")
        self.room_state = {}
        player_name = self._player_name()
        self._last_voice_ping_ts = 0.0
        self._smoothed_voice_level = 0.0
        self._last_chat_signature = None
        self._last_players_signature = None
        self._last_chat_mount_signature = None
        self._last_progress_signature = None
        self._last_overlay_geometry_signature = None
        self._leave_sent = False
        self._last_start_attempt_ts = 0.0
        self._start_game_request_in_flight = False
        self._local_starts_count = 0
        self._profile_cache = {}
        self._profile_cache_ts = 0.0
        self._poll_in_flight = False
        self._poll_reschedule = False
        self._poll_token = 0
        self._chat_request_in_flight = False
        self._skip_request_in_flight = False
        self._chat_request_token = 0
        self._skip_request_token = 0
        self._message_history = []
        self._last_message_id = 0
        self._set_mic_muted(True)
        self._set_mic_level(0.0)
        self.loading_overlay.hide()
        self.coin_badge.refresh_from_session()
        self.countdown_overlay.hide()
        # Safe defaults before server state arrives: hide start button, show wait label.
        self._set_button_visibility(self.start_game_btn, False)
        self.wait_host_btn.disabled = True
        self.wait_host_btn.opacity = 1
        self.wait_host_btn.text = "Ожидайте, пока объясняющий начнёт игру"
        self.explainer_status_label.text = "Загрузка комнаты..."
        self.players_label.text = ""
        self._join_failed = False
        self._consecutive_poll_failures = 0
        if self.room_code and player_name:
            self.explainer_status_label.text = "Подключение к комнате..."
            Thread(
                target=self._join_room_worker,
                args=(
                    self.room_code,
                    player_name,
                    bool(app is not None and getattr(app, "guest_mode", False)),
                    (app.resolve_client_id() if app is not None and hasattr(app, "resolve_client_id") else ""),
                ),
                daemon=True,
            ).start()
        self._start_polling()
        self._start_voice_ui_sync()
        self._start_voice_engine()
        self._poll_state()

    def on_leave(self, *_):
        self._stop_polling()
        self._stop_voice_ui_sync()
        self._stop_voice_engine()
        self.loading_overlay.hide()
        self.countdown_overlay.hide()
        self._dismiss_leave_popup()
        self._last_players_signature = None
        self._last_chat_mount_signature = None
        self._last_progress_signature = None
        self._last_overlay_geometry_signature = None
        self._poll_in_flight = False
        self._poll_reschedule = False
        self._poll_token += 1
        self._chat_request_in_flight = False
        self._skip_request_in_flight = False
        self._chat_request_token += 1
        self._skip_request_token += 1
        self._message_history = []
        self._last_message_id = 0
        self.disabled = True

    def _join_room_worker(self, room_code, player_name, is_guest, client_id):
        try:
            joined_room = join_online_room(
                room_code=room_code,
                player_name=player_name,
                is_guest=is_guest,
                client_id=client_id,
            )
            Clock.schedule_once(lambda dt: self._finish_join_room(joined_room), 0)
        except (ConnectionError, ValueError):
            Clock.schedule_once(lambda dt: self._finish_join_room(None), 0)

    def _finish_join_room(self, joined_room):
        if joined_room is None:
            self._join_failed = True
            self.explainer_status_label.text = "Не удалось подключиться."
            self._show_reconnect_banner()
            return
        app = App.get_running_app()
        if app is None:
            return
        joined_as = (joined_room.get("_joined_as") or "").strip()
        if joined_as and hasattr(app, "adopt_room_player_name"):
            app.adopt_room_player_name(joined_as)
        server_state = joined_room.get("_server_state")
        if isinstance(server_state, dict):
            initial_state = dict(server_state)
            incoming_messages = initial_state.get("messages") if isinstance(initial_state.get("messages"), list) else []
            initial_state["messages"] = self._merge_message_history(incoming_messages, since_id=0)
            self.room_state = initial_state
            app.set_active_room(initial_state.get("room", joined_room))
            self._apply_state()
        else:
            app.set_active_room(joined_room)
        self._join_failed = False
        self._consecutive_poll_failures = 0
        self._hide_reconnect_banner()

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
        # Grace period: if the round has been active for < 30s, no penalty
        round_timer = int((self.room_state or {}).get("round_timer_sec") or 0)
        round_left = int((self.room_state or {}).get("round_left_sec") or 0)
        elapsed_in_round = max(0, round_timer - round_left) if round_timer > 0 else 999
        in_grace_period = self._current_phase() == "round" and elapsed_in_round < 30
        if not in_grace_period and app is not None and hasattr(app, "apply_room_exit_penalty"):
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
                args=(room_code, player_name),
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

    def _leave_room_worker(self, room_code, player_name):
        try:
            leave_online_room(room_code=room_code, player_name=player_name)
        except (ConnectionError, ValueError):
            return

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

    def _player_name(self):
        app = App.get_running_app()
        return app.resolve_player_name() if app is not None else None

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
        if self._explainer_chat_locked():
            return False
        viewer = self._viewer_state()
        if viewer and "can_send_chat" in viewer:
            return bool(viewer.get("can_send_chat"))
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

    def _sync_players_grid_width(self, *_):
        cols = max(1, int(getattr(self.players_box, "cols", 1) or 1))
        total_spacing = self.players_box.spacing[0] * (cols - 1) if isinstance(self.players_box.spacing, (list, tuple)) else self.players_box.spacing * (cols - 1)
        total_padding = dp(8)
        available_width = max(dp(96), self.players_scroll.width - dp(12))
        min_width = dp(110) if self.players_box.row_default_height >= dp(120) else dp(86)
        column_width = max(min_width, (available_width - total_spacing - total_padding) / cols)
        self.players_box.col_default_width = column_width
        self.players_box.width = column_width * cols + total_spacing + total_padding

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

    def _start_polling(self):
        self._stop_polling()
        self._poll_event = Clock.schedule_interval(lambda _dt: self._poll_state(), 0.65)

    def _stop_polling(self):
        if self._poll_event is not None:
            self._poll_event.cancel()
            self._poll_event = None

    def _show_reconnect_banner(self):
        if getattr(self, "_reconnect_banner_visible", False):
            return
        self._reconnect_banner_visible = True
        self.status_label.color = COLORS["error"]
        self.status_label.text = "Соединение потеряно. Нажми «Переподключиться»."
        if not hasattr(self, "_reconnect_btn") or self._reconnect_btn is None:
            from ui.components import AppButton
            self._reconnect_btn = AppButton(
                text="Переподключиться",
                size_hint=(1, None),
                height=44,
            )
            self._reconnect_btn.bind(on_release=self._manual_reconnect)
        if self._reconnect_btn.parent is None:
            self.status_label.parent.add_widget(self._reconnect_btn, index=0)

    def _hide_reconnect_banner(self):
        self._reconnect_banner_visible = False
        if hasattr(self, "_reconnect_btn") and self._reconnect_btn is not None and self._reconnect_btn.parent is not None:
            self._reconnect_btn.parent.remove_widget(self._reconnect_btn)

    def _manual_reconnect(self, *_):
        self._consecutive_poll_failures = 0
        self._hide_reconnect_banner()
        self.explainer_status_label.text = "Переподключение..."
        player_name = (self._player_name() or "").strip()
        app = App.get_running_app()
        if self.room_code and player_name:
            Thread(
                target=self._join_room_worker,
                args=(
                    self.room_code,
                    player_name,
                    bool(app is not None and getattr(app, "guest_mode", False)),
                    (app.resolve_client_id() if app is not None and hasattr(app, "resolve_client_id") else ""),
                ),
                daemon=True,
            ).start()

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

    def _set_button_visibility(self, button, visible):
        button.disabled = not visible
        button.opacity = 1 if visible else 0

    def _set_panel_visibility(self, panel, visible, shown_height):
        panel.disabled = not visible
        panel.opacity = 1 if visible else 0
        panel.height = shown_height if visible else dp(0)

    def _can_wait_for_host_in_lobby(self):
        viewer = self._viewer_state()
        if viewer and "is_player" in viewer:
            return bool(viewer.get("is_player")) and not self._can_control_start()
        return bool(self._player_name()) and not self._can_control_start()

    def _show_lobby_action_row(self, phase):
        if phase != "lobby":
            return False
        return self._can_control_start() or self._can_wait_for_host_in_lobby()

    def _show_explainer_controls(self, is_explainer, phase):
        can_start = phase == "lobby" and self._can_control_start()
        waiting_for_host = phase == "lobby" and self._can_wait_for_host_in_lobby() and not can_start
        self._set_button_visibility(self.start_game_btn, can_start)
        self.wait_host_btn.disabled = True
        self.wait_host_btn.opacity = 1 if waiting_for_host else 0

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

    def _render_player_cards(self, players, explainer_name, host_name="", profile_map=None, score_map=None, phase="lobby"):
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

    def _poll_state(self):
        if self._poll_in_flight:
            self._poll_reschedule = True
            return

        room_code = (self.room_code or "").strip().upper()
        if not room_code:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Комната не выбрана. Создай комнату или зайди в существующую."
            return

        player_name = (self._player_name() or "").strip()
        if not player_name:
            self.status_label.color = COLORS["error"]
            self.status_label.text = "Сессия игрока не найдена. Войди в аккаунт снова."
            return

        self._poll_in_flight = True
        self._poll_token += 1
        request_token = self._poll_token
        since_id = int(self._last_message_id or 0)
        worker = Thread(
            target=self._poll_state_worker,
            args=(request_token, room_code, player_name, since_id),
            daemon=True,
        )
        worker.start()

    def _poll_state_worker(self, request_token, room_code, player_name, since_id):
        result = {
            "token": request_token,
            "room_code": room_code,
            "player_name": player_name,
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
        token = int(payload.get("token") or 0)
        if token != self._poll_token:
            return

        self._poll_in_flight = False
        if self.manager is None or self.manager.current != self.name:
            return

        if (payload.get("room_code") or "").strip().upper() != (self.room_code or "").strip().upper():
            return

        status = payload.get("status")
        if status == "success":
            self._consecutive_poll_failures = 0
            self._hide_reconnect_banner()
            state = dict(payload.get("state") or {})
            incoming_messages = state.get("messages") if isinstance(state.get("messages"), list) else []
            used_since = int(payload.get("since_id") or 0)
            state["messages"] = self._merge_message_history(incoming_messages, used_since)
            viewer_state = state.get("viewer") if isinstance(state.get("viewer"), dict) else {}
            if not viewer_state or "is_player" not in viewer_state:
                self.status_label.color = COLORS["warning"]
                self.status_label.text = "Сервер не прислал состояние игрока. Повтори вход в комнату."
                if self._poll_reschedule:
                    self._poll_reschedule = False
                    Clock.schedule_once(lambda *_: self._poll_state(), 0)
                return
            if not bool(viewer_state.get("is_player")):
                app = App.get_running_app()
                if app is not None:
                    app.clear_active_room()
                    if hasattr(app, "ensure_screen"):
                        app.ensure_screen("join_room")
                self.room_code = ""
                self.room_state = {}
                self.status_label.color = COLORS["warning"]
                self.status_label.text = "Ты больше не состоишь в этой комнате."
                Clock.schedule_once(lambda *_: setattr(self.manager, "current", "join_room"), 0)
                return
            self.room_state = state
            app = App.get_running_app()
            if app is not None:
                viewer_name = ((state.get("viewer") or {}).get("player_name") or "").strip()
                if viewer_name and hasattr(app, "adopt_room_player_name"):
                    app.adopt_room_player_name(viewer_name)
                app.set_active_room(state.get("room", {}))
            self._apply_state()
        elif status == "connection_error":
            self._consecutive_poll_failures += 1
            self.status_label.color = COLORS["error"]
            self.status_label.text = payload.get("message") or "Не удалось обновить комнату."
            if self._consecutive_poll_failures >= 3:
                self._show_reconnect_banner()
        elif status == "value_error":
            message = payload.get("message") or "Ошибка обновления комнаты."
            if "Player is not in this room." in message:
                app = App.get_running_app()
                if app is not None:
                    app.clear_active_room()
                    if hasattr(app, "ensure_screen"):
                        app.ensure_screen("join_room")
                self.room_code = ""
                self.room_state = {}
                self.status_label.color = COLORS["warning"]
                self.status_label.text = "Ты больше не в этой комнате. Зайди в нее снова."
                Clock.schedule_once(lambda *_: setattr(self.manager, "current", "join_room"), 0)
            else:
                self.status_label.color = COLORS["warning"]
                self.status_label.text = message
        else:
            self.status_label.color = COLORS["error"]
            self.status_label.text = payload.get("message") or "Не удалось обновить состояние комнаты."

        if self._poll_reschedule:
            self._poll_reschedule = False
            Clock.schedule_once(lambda *_: self._poll_state(), 0)

    def _apply_state(self):
        room = self.room_state.get("room", {})
        players = self.room_state.get("players", [])
        scores = self.room_state.get("scores", [])
        messages = self.room_state.get("messages", [])
        viewer = self._viewer_state()

        player_name = self._player_name() or ""
        is_explainer = self._is_explainer()
        phase = self._current_phase()
        self._set_room_exit_button(self._is_match_active())
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
        profile_map = self._profile_map()
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

        round_active = phase == "round"
        self.brand_title.height = dp(0) if round_active else self.brand_title_height
        self.brand_title.opacity = 0 if round_active else 1
        if phase == "round":
            self.chat_card._bg_color.rgba = (0.05, 0.09, 0.15, 0.24 if is_explainer else 0.30)
            self.chat_card._border_color.rgba = (1, 1, 1, 0.08)
            self.chat_card._shadow_color.rgba = (0, 0, 0, 0.05)
            self.chat_title.color = COLORS["text"]
        else:
            self.chat_card._bg_color.rgba = COLORS["surface"]
            self.chat_card._border_color.rgba = COLORS["outline"]
            self.chat_card._shadow_color.rgba = (0, 0, 0, 0.24)
            self.chat_title.color = COLORS["text"]

        can_chat = self._can_send_chat()
        if explainer_can_only_voice:
            self._set_word_text(self.room_state.get("current_word"))
            self.chat_input.hint_text = "Объясняющий не пишет в чат."
            self._set_mic_enabled(self._can_toggle_mic())
        else:
            self._set_word_text("Слово скрыто")
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
                self.explainer_status_label.text = f"Ты — объясняющий | Нажми «Начать игру»"
            else:
                self.explainer_status_label.text = f"Ты — угадывающий | Объясняет: {explainer_name}"
            self.wait_host_btn.text = f"Ожидайте, пока {explainer_name} начнёт игру"
        else:
            self.explainer_status_label.text = f"Объясняет слова: {explainer_name} | Микрофон: {mic_state_text}"

        self._show_explainer_controls(is_explainer, phase)
        show_players_grid = phase in {"lobby", "round"}
        players_panel_height = self.players_wrap_round_height if phase == "round" else self.players_wrap_height
        scores_panel_height = self.scores_wrap_overlay_height if phase == "round" and is_explainer else self.scores_wrap_height
        self._set_panel_visibility(self.room_meta_wrap, phase not in {"lobby", "round"} and not is_explainer, self.room_meta_wrap_height)
        self._set_panel_visibility(self.players_wrap, show_players_grid, players_panel_height)
        self._set_panel_visibility(self.players_summary_wrap, False, self.players_summary_wrap_height)
        self._set_panel_visibility(
            self.lobby_start_row,
            self._show_lobby_action_row(phase),
            self.lobby_start_height,
        )
        self._set_panel_visibility(self.explainer_card, phase in {"countdown", "round"} and not is_explainer, self.explainer_card_height)
        self._set_panel_visibility(self.word_stage, phase == "round" and is_explainer, self.word_stage_height)
        self._set_panel_visibility(self.voice_card, False, self.voice_card_height)
        self._set_panel_visibility(self.scores_wrap, phase == "round" and is_explainer, scores_panel_height)
        self._set_panel_visibility(self.phase_wrap, phase in {"countdown", "round"}, self.phase_wrap_height)
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
            self.countdown_overlay.hide()
        elif phase == "countdown":
            self.phase_label.color = COLORS["accent"]
            self.phase_label.text = f"СТАРТ ЧЕРЕЗ {countdown_left} СЕК"
            if countdown_left > 0:
                self.countdown_overlay.show(countdown_left)
            else:
                self.countdown_overlay.show(1)
        else:
            self.phase_label.color = COLORS["success"]
            self.phase_label.text = f"ОСТАЛОСЬ {round_left} СЕК"
            self.countdown_overlay.hide()

        self._render_player_cards(players, explainer_name, host_name, profile_map, score_map, phase)
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

    def _credit_local_coins(self, amount):
        """Immediately credit earned coins to the local profile / guest balance."""
        app = App.get_running_app()
        if app is None or amount <= 0:
            return
        if getattr(app, "authenticated", False):
            profile = app.current_profile()
            if profile is not None:
                new_balance = int(getattr(profile, "alias_coins", 0) or 0) + amount
                self.coin_badge.set_value(new_balance)
        else:
            current = int(getattr(app, "guest_alias_coins", 0) or 0)
            app.guest_alias_coins = current + amount
            self.coin_badge.set_value(app.guest_alias_coins)

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

    def _queue_start_game(self, *_):
        now_ts = time.time()
        if self._start_game_request_in_flight or now_ts - self._last_start_attempt_ts < 0.35:
            return
        self._last_start_attempt_ts = now_ts
        self._start_game()

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

    def _start_game(self, *_):
        if self._current_phase() != "lobby":
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Игра уже запущена."
            return
        if not self._can_control_start():
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Начать игру может только создатель комнаты."
            return

        player_name = self._player_name()
        if not player_name or not self.room_code:
            self.status_label.color = COLORS["error"]
            self.status_label.text = "Не удалось определить игрока для старта игры."
            return

        room_before_start = self.room_state.get("room", {}) if isinstance(self.room_state, dict) else {}
        try:
            starts_before = int((room_before_start or {}).get("starts_count") or 0)
        except (TypeError, ValueError):
            starts_before = 0
        starts_before = max(starts_before, int(self._local_starts_count or 0))
        should_charge_by_local_state = starts_before >= 1

        app = App.get_running_app()
        profile = app.current_profile() if app is not None and getattr(app, "authenticated", False) else None
        if should_charge_by_local_state:
            if profile is not None:
                try:
                    current_coins = int(getattr(profile, "alias_coins", 0) or 0)
                except (TypeError, ValueError):
                    current_coins = 0
                if current_coins < ROOM_CREATION_COST:
                    self.status_label.color = COLORS["warning"]
                    self.status_label.text = (
                        f"Нужно минимум {ROOM_CREATION_COST} AC для запуска игры. Сейчас: {current_coins} AC."
                    )
                    return
            elif app is not None and getattr(app, "guest_mode", False):
                current_coins = int(app.current_alias_coins() or 0)
                if current_coins < ROOM_CREATION_COST:
                    self.status_label.color = COLORS["warning"]
                    self.status_label.text = (
                        f"Нужно минимум {ROOM_CREATION_COST} AC для запуска игры. Сейчас: {current_coins} AC."
                    )
                    return

        self._start_game_request_in_flight = True
        self.start_game_btn.disabled = True
        self.loading_overlay.show("Запускаем игру...")

        try:
            start_response = start_room_game(room_code=self.room_code, player_name=player_name)
        except ConnectionError as error:
            self.status_label.color = COLORS["error"]
            self.status_label.text = str(error)
            self._start_game_request_in_flight = False
            self.start_game_btn.disabled = False
            self.loading_overlay.hide()
            return
        except ValueError as error:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = str(error)
            self._start_game_request_in_flight = False
            self.start_game_btn.disabled = False
            self.loading_overlay.hide()
            return

        updated_state = dict(self.room_state or {})
        if isinstance(start_response, dict):
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

        room_payload = updated_state.get("room") if isinstance(updated_state, dict) else {}
        try:
            starts_count = int((room_payload or {}).get("starts_count") or 0)
        except (TypeError, ValueError):
            starts_count = 0
        should_charge_start = starts_count > 1 or should_charge_by_local_state
        self._local_starts_count = max(starts_count, starts_before + 1)

        charge_payload = None
        if should_charge_start:
            charged, charge_payload = self._charge_start_cost()
            if not charged:
                self._start_game_request_in_flight = False
                self.start_game_btn.disabled = False
                self.loading_overlay.hide()
                self.status_label.color = COLORS["warning"]
                self.status_label.text = str(charge_payload)
                return

        self._start_game_request_in_flight = False
        self.loading_overlay.hide()
        self.status_label.color = COLORS["success"]
        if should_charge_start and charge_payload is not None:
            remaining_coins = int(getattr(charge_payload, "alias_coins", 0) or 0)
            self.status_label.text = (
                f"Старт игры! Списано {ROOM_CREATION_COST} AC, осталось {remaining_coins} AC."
            )
        else:
            self.status_label.text = "Старт игры! Первый запуск в этой комнате бесплатный."
        self._poll_state()

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

        worker = Thread(
            target=self._send_chat_worker,
            args=(request_token, phase, self.room_code, player_name, text),
            daemon=True,
        )
        worker.start()

    def _send_chat_worker(self, request_token, phase, room_code, player_name, text):
        payload = {
            "token": request_token,
            "phase": phase,
            "status": "error",
            "tone": "error",
            "message": "Не удалось отправить сообщение.",
        }
        try:
            if phase == "round":
                result = send_room_guess(room_code=room_code, player_name=player_name, guess=text)
                payload = {
                    "token": request_token,
                    "phase": phase,
                    "status": "success",
                    "result": result,
                }
            else:
                send_room_chat(room_code=room_code, player_name=player_name, message=text)
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
                coin_guesser = int(result.get("coin_reward_guesser") or 0)
                coin_explainer = int(result.get("coin_reward_explainer") or 0)
                my_name = self._player_name() or ""
                my_coins = 0
                if my_name.strip().lower() == (guesser_player or "").strip().lower():
                    my_coins = coin_guesser
                elif my_name.strip().lower() == (awarded_player or "").strip().lower():
                    my_coins = coin_explainer
                coin_msg = f" (+{my_coins} AC)" if my_coins else ""
                self.status_label.color = COLORS["success"]
                self.status_label.text = f"Верно! {awarded_player} +1 и {guesser_player} +1.{coin_msg}"
                if my_coins:
                    self._credit_local_coins(my_coins)
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
            if "scores" in result:
                updated_state["scores"] = result.get("scores") or []
            if "current_word" in result:
                updated_state["current_word"] = result.get("current_word") or ""
            self.room_state = updated_state
            self._apply_state()

        self.chat_input.text = ""
        self._poll_state()

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
        worker = Thread(
            target=self._skip_word_worker,
            args=(request_token, self.room_code, player_name),
            daemon=True,
        )
        worker.start()

    def _skip_word_worker(self, request_token, room_code, player_name):
        payload = {
            "token": request_token,
            "status": "error",
            "tone": "error",
            "message": "Не удалось скипнуть слово.",
        }
        try:
            response = skip_room_word(room_code=room_code, player_name=player_name)
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
        if not self._can_toggle_mic():
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Микрофон доступен только тому, кто объясняет слова."
            return

        player_name = self._player_name()
        if not player_name or not self.room_code:
            self.status_label.color = COLORS["error"]
            self.status_label.text = "Не удалось определить игрока или комнату."
            return

        old_muted = self._mic_is_muted()
        new_muted = not old_muted
        self._set_mic_muted(new_muted)

        try:
            response = set_room_mic_state(
                room_code=self.room_code,
                player_name=player_name,
                muted=new_muted,
            )
        except ConnectionError as error:
            self._set_mic_muted(old_muted)
            self.status_label.color = COLORS["error"]
            self.status_label.text = str(error)
            return
        except ValueError as error:
            self._set_mic_muted(old_muted)
            self.status_label.color = COLORS["warning"]
            self.status_label.text = str(error)
            return

        updated_state = dict(self.room_state or {})
        if isinstance(response, dict):
            for key in ("room", "voice_active", "voice_speaker", "explainer_mic_state", "server_time"):
                if key in response:
                    updated_state[key] = response.get(key)

            room_payload = response.get("room")
            if isinstance(room_payload, dict) and "explainer_mic_muted" in room_payload:
                updated_state["explainer_mic_muted"] = bool(room_payload.get("explainer_mic_muted"))
            elif "muted" in response:
                updated_state["explainer_mic_muted"] = bool(response.get("muted"))

        self.room_state = updated_state
        self._set_mic_muted(bool(updated_state.get("explainer_mic_muted", new_muted)))

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
            ping_room_voice(room_code=self.room_code, player_name=player_name, active_seconds=3)
        except (ConnectionError, ValueError):
            pass
