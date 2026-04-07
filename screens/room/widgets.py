"""Custom widget classes for the room screen."""

from pathlib import Path

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.graphics import Color, Ellipse, Line, Rectangle
from kivy.metrics import dp, sp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.widget import Widget

from ui import AvatarButton, BodyLabel, COLORS, PixelLabel, RoundedPanel


MIC_ICON_PATH = Path(__file__).resolve().parents[2] / "image" / "mic_white.png"


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
        self.disabled = False
        number = max(1, int(seconds_left))
        self._label.text = str(number)
        self._caption.text = "СТАРТ ЧЕРЕЗ"
        self._sync_canvas()

    def hide(self):
        self._active = False
        self.opacity = 0
        self.disabled = True
        self._label.text = ""

    def on_touch_down(self, touch):
        return False

    def on_touch_move(self, touch):
        return False

    def on_touch_up(self, touch):
        return False
