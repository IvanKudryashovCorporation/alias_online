from pathlib import Path

from kivy.animation import Animation
from kivy.app import App
from kivy.clock import Clock
from kivy.graphics import (
    Color,
    Ellipse,
    Line,
    PopMatrix,
    PushMatrix,
    Rectangle,
    Rotate,
    RoundedRectangle,
    StencilPop,
    StencilPush,
    StencilUnUse,
    StencilUse,
    Triangle,
)
from kivy.metrics import dp, sp
from kivy.utils import platform
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

from .theme import BACKGROUND_PATH, COLORS, radius, register_game_font
from .feedback import trigger_tap_feedback


def resolve_image_source(source):
    raw_source = (source or "").strip()
    if not raw_source:
        return ""

    if raw_source.startswith(("http://", "https://", "file://")):
        return raw_source

    candidate = Path(raw_source).expanduser()
    if candidate.exists():
        return candidate.resolve().as_posix()

    return raw_source


class ScreenBackground(FloatLayout):
    def __init__(self, variant="lobby", **kwargs):
        kwargs.setdefault("size_hint", (1, 1))
        super().__init__(**kwargs)
        self.variant = (variant or "lobby").strip().lower()
        self._bound_parent = None

        self._background_image = Image(source=str(BACKGROUND_PATH), fit_mode="fill")
        # Use only programmatic scene layers on all screens.
        self._background_image.opacity = 0
        self.add_widget(self._background_image)

        self._scene = Widget()
        with self._scene.canvas.before:
            sky_color = COLORS["game_sky"] if self.variant == "game" else COLORS["lobby_sky"]
            self._sky_color = Color(*sky_color)
            self._sky_rect = Rectangle(pos=self.pos, size=self.size)
            if self.variant == "game":
                self._scene_shadow_color = Color(0.04, 0.10, 0.16, 0.08)
                self._scene_shadow = Rectangle(pos=self.pos, size=self.size)

                self._spotlight_color = Color(*COLORS["game_spotlight"])
                self._spotlight_left = Triangle()
                self._spotlight_center = Triangle()
                self._spotlight_right = Triangle()

                self._game_card_blue_color = Color(*COLORS["game_card_blue"])
                self._game_card_blue = RoundedRectangle(radius=radius(14))
                self._game_card_gold_color = Color(*COLORS["game_card_gold"])
                self._game_card_gold = RoundedRectangle(radius=radius(14))
                self._game_card_cyan_color = Color(*COLORS["game_card_cyan"])
                self._game_card_cyan = RoundedRectangle(radius=radius(14))

                self._game_card_outline_color = Color(*COLORS["game_card_outline"])
                self._game_card_blue_outline = Line(width=1.1)
                self._game_card_gold_outline = Line(width=1.1)
                self._game_card_cyan_outline = Line(width=1.1)

                self._token_orange_color = Color(*COLORS["game_token_orange"])
                self._token_orange = Ellipse()
                self._token_mint_color = Color(*COLORS["game_token_mint"])
                self._token_mint = Ellipse()

                self._stage_glow_color = Color(*COLORS["game_stage_glow"])
                self._stage_glow = Ellipse()
                self._stage_color = Color(*COLORS["game_stage"])
                self._stage = RoundedRectangle(radius=radius(34))
            else:
                self._scene_shadow_color = Color(*COLORS["scene_shadow"])
                self._scene_shadow = Rectangle(pos=self.pos, size=self.size)

                self._back_hill_color = Color(*COLORS["scene_back_hill"])
                self._back_hill_left = Ellipse()
                self._back_hill_mid = Ellipse()
                self._back_hill_right = Ellipse()

                self._house_blue_color = Color(*COLORS["scene_house_blue"])
                self._house_blue = Rectangle()
                self._house_cream_color = Color(*COLORS["scene_house_cream"])
                self._house_cream = Rectangle()
                self._house_mint_color = Color(*COLORS["scene_house_mint"])
                self._house_mint = Rectangle()
                self._house_yellow_color = Color(*COLORS["scene_house_yellow"])
                self._house_yellow = Rectangle()

                self._roof_color = Color(*COLORS["scene_roof"])
                self._roof_blue = Triangle()
                self._roof_cream = Triangle()
                self._roof_mint = Triangle()
                self._roof_yellow = Triangle()

                self._front_hill_color = Color(*COLORS["scene_front_hill"])
                self._front_hill_left = Ellipse()
                self._front_hill_mid = Ellipse()
                self._front_hill_right = Ellipse()
        self._scene.bind(pos=self._sync_scene, size=self._sync_scene)
        self.add_widget(self._scene)

        self._overlay = Widget()
        with self._overlay.canvas.before:
            overlay_color = COLORS["game_overlay"] if self.variant == "game" else COLORS["overlay"]
            self._overlay_color = Color(*overlay_color)
            self._overlay_rect = Rectangle(pos=self._overlay.pos, size=self._overlay.size)
        self._overlay.bind(pos=self._sync_overlay, size=self._sync_overlay)
        self.add_widget(self._overlay)

        self.bind(parent=self._bind_parent_geometry)
        Clock.schedule_once(self._sync_parent_geometry, 0)

    def _bind_parent_geometry(self, *_):
        parent = self.parent
        if self._bound_parent is parent:
            return

        if self._bound_parent is not None:
            self._bound_parent.unbind(pos=self._sync_parent_geometry, size=self._sync_parent_geometry)

        self._bound_parent = parent
        if parent is None:
            return

        parent.bind(pos=self._sync_parent_geometry, size=self._sync_parent_geometry)
        self._sync_parent_geometry()

    def _sync_parent_geometry(self, *_):
        parent = self.parent
        if parent is None:
            return

        parent_size = tuple(parent.size)
        parent_pos = tuple(parent.pos)
        if tuple(self.size) != parent_size:
            self.size = parent_size
        if tuple(self.pos) != parent_pos:
            self.pos = parent_pos

    def _sync_overlay(self, *_):
        self._overlay_rect.pos = self._overlay.pos
        self._overlay_rect.size = self._overlay.size

    def _sync_scene(self, *_):
        if self.variant == "game":
            self._sync_game_scene()
            return

        self._sync_lobby_scene()

    def _sync_lobby_scene(self):
        width = self._scene.width
        height = self._scene.height
        x = self._scene.x
        y = self._scene.y

        self._sky_rect.pos = (x, y)
        self._sky_rect.size = (width, height)
        self._scene_shadow.pos = (x, y)
        self._scene_shadow.size = (width, height * 0.22)

        back_y = y - height * 0.01
        back_h = height * 0.24
        self._back_hill_left.pos = (x - width * 0.16, back_y + height * 0.05)
        self._back_hill_left.size = (width * 0.58, back_h)
        self._back_hill_mid.pos = (x + width * 0.20, back_y + height * 0.07)
        self._back_hill_mid.size = (width * 0.60, back_h * 1.05)
        self._back_hill_right.pos = (x + width * 0.58, back_y + height * 0.05)
        self._back_hill_right.size = (width * 0.50, back_h)

        house_base_y = y + height * 0.10
        house1 = (x + width * 0.11, house_base_y, width * 0.09, height * 0.11)
        house2 = (x + width * 0.30, house_base_y, width * 0.11, height * 0.14)
        house3 = (x + width * 0.51, house_base_y, width * 0.10, height * 0.12)
        house4 = (x + width * 0.71, house_base_y, width * 0.09, height * 0.13)

        self._house_blue.pos = house1[:2]
        self._house_blue.size = house1[2:]
        self._house_cream.pos = house2[:2]
        self._house_cream.size = house2[2:]
        self._house_mint.pos = house3[:2]
        self._house_mint.size = house3[2:]
        self._house_yellow.pos = house4[:2]
        self._house_yellow.size = house4[2:]

        self._roof_blue.points = [
            house1[0] - width * 0.01,
            house1[1] + house1[3],
            house1[0] + house1[2] * 0.5,
            house1[1] + house1[3] + height * 0.035,
            house1[0] + house1[2] + width * 0.01,
            house1[1] + house1[3],
        ]
        self._roof_cream.points = [
            house2[0] - width * 0.01,
            house2[1] + house2[3],
            house2[0] + house2[2] * 0.5,
            house2[1] + house2[3] + height * 0.038,
            house2[0] + house2[2] + width * 0.01,
            house2[1] + house2[3],
        ]
        self._roof_mint.points = [
            house3[0] - width * 0.01,
            house3[1] + house3[3],
            house3[0] + house3[2] * 0.5,
            house3[1] + house3[3] + height * 0.032,
            house3[0] + house3[2] + width * 0.01,
            house3[1] + house3[3],
        ]
        self._roof_yellow.points = [
            house4[0] - width * 0.01,
            house4[1] + house4[3],
            house4[0] + house4[2] * 0.5,
            house4[1] + house4[3] + height * 0.030,
            house4[0] + house4[2] + width * 0.01,
            house4[1] + house4[3],
        ]

        front_y = y - height * 0.05
        front_h = height * 0.22
        self._front_hill_left.pos = (x - width * 0.20, front_y)
        self._front_hill_left.size = (width * 0.56, front_h)
        self._front_hill_mid.pos = (x + width * 0.18, front_y + height * 0.01)
        self._front_hill_mid.size = (width * 0.60, front_h * 1.02)
        self._front_hill_right.pos = (x + width * 0.58, front_y)
        self._front_hill_right.size = (width * 0.56, front_h)

    def _sync_game_scene(self):
        width = self._scene.width
        height = self._scene.height
        x = self._scene.x
        y = self._scene.y

        self._sky_rect.pos = (x, y)
        self._sky_rect.size = (width, height)
        self._scene_shadow.pos = (x, y)
        self._scene_shadow.size = (width, height * 0.24)

        top_y = y + height
        beam_bottom_y = y + height * 0.34
        self._spotlight_left.points = [
            x + width * 0.05,
            top_y,
            x + width * 0.22,
            top_y,
            x + width * 0.36,
            beam_bottom_y,
        ]
        self._spotlight_center.points = [
            x + width * 0.40,
            top_y,
            x + width * 0.60,
            top_y,
            x + width * 0.50,
            y + height * 0.40,
        ]
        self._spotlight_right.points = [
            x + width * 0.78,
            top_y,
            x + width * 0.95,
            top_y,
            x + width * 0.64,
            beam_bottom_y,
        ]

        stage_w = width * 0.74
        stage_h = height * 0.115
        stage_x = x + (width - stage_w) * 0.5
        stage_y = y + height * 0.06
        self._stage.pos = (stage_x, stage_y)
        self._stage.size = (stage_w, stage_h)
        self._stage_glow.pos = (stage_x - width * 0.08, stage_y - height * 0.05)
        self._stage_glow.size = (stage_w + width * 0.16, stage_h + height * 0.12)

        blue_card = (x + width * 0.12, y + height * 0.18, width * 0.17, height * 0.11)
        gold_card = (x + width * 0.73, y + height * 0.20, width * 0.15, height * 0.10)
        cyan_card = (x + width * 0.62, y + height * 0.52, width * 0.13, height * 0.09)

        self._game_card_blue.pos = blue_card[:2]
        self._game_card_blue.size = blue_card[2:]
        self._game_card_gold.pos = gold_card[:2]
        self._game_card_gold.size = gold_card[2:]
        self._game_card_cyan.pos = cyan_card[:2]
        self._game_card_cyan.size = cyan_card[2:]

        self._game_card_blue_outline.rounded_rectangle = (*blue_card, dp(14))
        self._game_card_gold_outline.rounded_rectangle = (*gold_card, dp(14))
        self._game_card_cyan_outline.rounded_rectangle = (*cyan_card, dp(14))

        self._token_orange.pos = (x + width * 0.24, y + height * 0.58)
        self._token_orange.size = (width * 0.09, width * 0.09)
        self._token_mint.pos = (x + width * 0.78, y + height * 0.42)
        self._token_mint.size = (width * 0.07, width * 0.07)


class TouchPassthroughFloatLayout(FloatLayout):
    """FloatLayout that does not steal touches when collapsed or fully transparent."""

    def on_touch_down(self, touch):
        if self.disabled or self.opacity < 0.01 or self.height < 1:
            return False
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if self.disabled or self.opacity < 0.01 or self.height < 1:
            return False
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if self.disabled or self.opacity < 0.01 or self.height < 1:
            return False
        return super().on_touch_up(touch)


class RoundedPanel(BoxLayout):
    def __init__(self, bg_color=None, shadow_alpha=0.24, **kwargs):
        super().__init__(**kwargs)

        bg_color = bg_color or COLORS["surface"]
        self._corner_radius = dp(22)

        with self.canvas.before:
            self._shadow_color = Color(0, 0, 0, shadow_alpha)
            self._shadow_rect = RoundedRectangle(radius=radius(24))
            self._bg_color = Color(*bg_color)
            self._bg_rect = RoundedRectangle(radius=radius(22))
            self._border_color = Color(*COLORS["outline"])
            self._border_line = Line(width=1.2)

        self.bind(pos=self._sync_canvas, size=self._sync_canvas)

    def _sync_canvas(self, *_):
        self._shadow_rect.pos = (self.x, self.y - dp(4))
        self._shadow_rect.size = self.size
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size
        self._border_line.rounded_rectangle = (self.x, self.y, self.width, self.height, self._corner_radius)


class AppButton(ButtonBehavior, Label):
    def __init__(self, text="", compact=False, **kwargs):
        register_game_font()
        font_size = kwargs.pop("font_size", sp(13 if compact else 18))
        button_color = kwargs.pop("button_color", COLORS["button"])
        pressed_color = kwargs.pop("pressed_color", COLORS["button_pressed"])
        super().__init__(**kwargs)

        self.text = text
        self.font_name = "GameFont"
        self.font_size = font_size
        self.color = COLORS["text"]
        self.halign = "center"
        self.valign = "middle"
        self.size_hint_y = None
        self.height = dp(54 if compact else 72)

        self._corner_radius = dp(22)
        self._rest_button_color = button_color
        self._pressed_button_color = pressed_color

        with self.canvas.before:
            self._shadow_color = Color(0, 0, 0, 0.34)
            self._shadow_rect = RoundedRectangle(radius=radius(24))
            self._button_color = Color(*self._rest_button_color)
            self._button_rect = RoundedRectangle(radius=radius(22))
            self._border_color = Color(*COLORS["outline"])
            self._border_line = Line(width=1.2)

        self.bind(pos=self._sync_canvas, size=self._sync_canvas)
        self.bind(size=self._sync_text)

    def _sync_canvas(self, *_):
        self._shadow_rect.pos = (self.x, self.y - dp(4))
        self._shadow_rect.size = self.size
        self._button_rect.pos = self.pos
        self._button_rect.size = self.size
        self._border_line.rounded_rectangle = (self.x, self.y, self.width, self.height, self._corner_radius)

    def _sync_text(self, *_):
        self.text_size = (max(0, self.width - dp(30)), max(0, self.height - dp(18)))

    def on_press(self):
        if self.disabled:
            return
        trigger_tap_feedback(play_sound=True, haptic=True)
        Animation.cancel_all(self._button_color)
        Animation(rgba=self._pressed_button_color, duration=0.08).start(self._button_color)

    def on_release(self):
        if self.disabled:
            return
        Animation.cancel_all(self._button_color)
        Animation(rgba=self._rest_button_color, duration=0.12).start(self._button_color)


class AppTextInput(TextInput):
    def __init__(self, **kwargs):
        register_game_font()
        multiline = kwargs.pop("multiline", False)
        height = kwargs.pop("height", dp(58 if not multiline else 144))
        input_font_name = kwargs.pop("font_name", "Roboto")
        input_type = kwargs.pop("input_type", "text")
        input_filter = kwargs.pop("input_filter", None)
        keyboard_suggestions = kwargs.pop("keyboard_suggestions", None)
        password_mode = bool(kwargs.get("password", False))
        if keyboard_suggestions is None:
            # Keep typing predictable on mobile keyboards (no unexpected auto-replacements).
            keyboard_suggestions = False if platform in {"android", "ios"} else not password_mode
        super().__init__(
            multiline=multiline,
            font_name=input_font_name,
            font_size=sp(16),
            size_hint_y=None,
            height=height,
            padding=[dp(16), dp(14), dp(16), dp(14)],
            background_normal="",
            background_active="",
            # Hide default rectangular Kivy background: rounded surface is drawn in canvas.before.
            background_color=(0, 0, 0, 0),
            foreground_color=COLORS["input_text"],
            disabled_foreground_color=COLORS["input_text"],
            hint_text_color=(0.20, 0.24, 0.30, 0.96),
            cursor_color=COLORS["input_text"],
            selection_color=(0.18, 0.22, 0.3, 0.22),
            use_bubble=False,
            use_handles=False,
            write_tab=False,
            input_type=input_type,
            input_filter=input_filter,
            keyboard_suggestions=keyboard_suggestions,
            **kwargs,
        )

        self._corner_radius = dp(22)
        self._base_hint_color = (0.22, 0.26, 0.32, 1)
        self._muted_hint_color = (0.28, 0.33, 0.40, 1)
        self._color_guard_events = []
        self._persistent_guard_event = None
        self._last_text_color = COLORS["input_text"]
        self._last_hint_color = self._base_hint_color

        with self.canvas.before:
            self._stencil_push = StencilPush()
            self._stencil_mask = RoundedRectangle(radius=radius(22))
            self._stencil_use = StencilUse()
            self._bg_color = Color(*COLORS["input_bg"])
            self._bg_rect = RoundedRectangle(radius=radius(22))
            self._border_color = Color(*COLORS["outline"])
            self._border_line = Line(width=1.1)
        with self.canvas.after:
            self._stencil_unuse = StencilUnUse()
            self._stencil_unmask = RoundedRectangle(radius=radius(22))
            self._stencil_pop = StencilPop()

        self.bind(pos=self._sync_canvas, size=self._sync_canvas)
        self.bind(readonly=self._apply_surface_palette)
        self.bind(disabled=self._apply_surface_palette)
        self.bind(focus=self._apply_surface_palette)
        self.bind(readonly=self._refresh_text_colors)
        self.bind(disabled=self._refresh_text_colors)
        self.bind(focus=self._refresh_text_colors)
        self.bind(text=self._ensure_visible_text)
        self.bind(focus=self._schedule_color_guard)
        self.bind(focus=self._enforce_mobile_text_input_mode)
        self.bind(parent=self._handle_parent_change)
        self._apply_surface_palette()
        self._refresh_text_colors()
        self._ensure_visible_text()
        self._enforce_mobile_text_input_mode()
        self._handle_parent_change()

    def _apply_surface_palette(self, *_):
        if self.readonly:
            bg_color = COLORS["input_readonly_bg"]
            border_color = COLORS["input_readonly_outline"]
            cursor_color = (0, 0, 0, 0)
        elif self.disabled:
            bg_color = COLORS["input_readonly_bg"]
            border_color = COLORS["outline_soft"]
            cursor_color = (0, 0, 0, 0)
        else:
            bg_color = COLORS["input_bg"]
            border_color = COLORS["outline"] if not self.focus else (0.38, 0.63, 0.96, 0.74)
            cursor_color = COLORS["input_text"]

        self.cursor_color = cursor_color
        self._bg_color.rgba = bg_color
        self._border_color.rgba = border_color

    def _refresh_text_colors(self, *_):
        text_color = COLORS["input_readonly_text"] if self.readonly or self.disabled else COLORS["input_text"]
        hint_color = self._muted_hint_color if self.readonly or self.disabled else self._base_hint_color
        self._last_text_color = text_color
        self._last_hint_color = hint_color
        self.foreground_color = text_color
        self.disabled_foreground_color = text_color
        self.cursor_color = (0, 0, 0, 0) if self.readonly or self.disabled else COLORS["input_text"]
        self.hint_text_color = hint_color
        self._apply_internal_label_palette(text_color, hint_color)

    def _ensure_visible_text(self, *_):
        # Mobile keyboards sometimes reset TextInput foreground color dynamically.
        # Force the expected high-contrast palette each time text changes.
        self._refresh_text_colors()
        self._force_text_refresh()

    def _schedule_color_guard(self, *_):
        # On some Android keyboards, TextInput color may reset after focus/keyboard transitions.
        # Re-apply palette a few ticks later to keep text readable.
        for event in self._color_guard_events:
            try:
                event.cancel()
            except Exception:
                pass
        self._color_guard_events = []
        for delay in (0, 0.06, 0.22, 0.52):
            self._color_guard_events.append(Clock.schedule_once(self._enforce_text_palette, delay))

    def _enforce_text_palette(self, *_):
        self._refresh_text_colors()
        self._force_text_refresh()

    def _apply_internal_label_palette(self, text_color, hint_color):
        # Some Android keyboard providers may repaint internal labels with their own palette.
        # Keep the visible glyph layers in sync with the configured input palette.
        try:
            labels = list(getattr(self, "_lines_labels", []) or [])
        except Exception:
            labels = []
        for label in labels:
            if label is None:
                continue
            try:
                label.color = text_color
                label.texture_update()
            except Exception:
                pass
        hint_label = getattr(self, "_hint_text_label", None)
        if hint_label is not None:
            try:
                hint_label.color = hint_color
                hint_label.texture_update()
            except Exception:
                pass

    def _force_text_refresh(self):
        try:
            self._refresh_text(self.text)
        except Exception:
            pass
        try:
            self._trigger_update_graphics()
        except Exception:
            pass

    def _handle_parent_change(self, *_):
        if self.parent is None:
            if self._persistent_guard_event is not None:
                self._persistent_guard_event.cancel()
                self._persistent_guard_event = None
            return

        if self._persistent_guard_event is None:
            self._persistent_guard_event = Clock.schedule_interval(self._persistent_palette_guard_tick, 0.45)
        self._schedule_color_guard()

    def _persistent_palette_guard_tick(self, *_):
        if self.parent is None:
            if self._persistent_guard_event is not None:
                self._persistent_guard_event.cancel()
                self._persistent_guard_event = None
            return False
        self._enforce_text_palette()
        return True

    def _sync_canvas(self, *_):
        self._stencil_mask.pos = self.pos
        self._stencil_mask.size = self.size
        self._stencil_unmask.pos = self.pos
        self._stencil_unmask.size = self.size
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size
        self._border_line.rounded_rectangle = (self.x, self.y, self.width, self.height, self._corner_radius)

    def _enforce_mobile_text_input_mode(self, *_):
        if platform not in {"android", "ios"}:
            return

        # Keep locale keyboard available (RU/EN switch) and avoid sticky ASCII-only mode.
        if self.input_type != "text":
            self.input_type = "text"
        self.input_filter = None


class BrandTitle(Widget):
    def __init__(self, text="ALIAS\nONLINE", font_size=None, shadow_step=None, layers=None, **kwargs):
        register_game_font()
        height = kwargs.pop("height", dp(320))
        super().__init__(size_hint_y=None, height=height, **kwargs)

        self._font_size = font_size or sp(62)
        self._shadow_step = shadow_step or dp(4)
        self._shadow_offsets = layers or [
            (0, -self._shadow_step),
            (self._shadow_step, -self._shadow_step),
        ]

        self._shadow_layers = []
        for dx, dy in self._shadow_offsets:
            shadow = Label(
                text=text,
                font_name="BrandFont",
                font_size=self._font_size,
                color=(0, 0, 0, 0.96),
                halign="center",
                valign="middle",
            )
            shadow._offset = (dx, dy)
            self._shadow_layers.append(shadow)
            self.add_widget(shadow)

        self._main_title = Label(
            text=text,
            font_name="BrandFont",
            font_size=self._font_size,
            color=COLORS["accent"],
            halign="center",
            valign="middle",
        )
        self.add_widget(self._main_title)
        self.bind(pos=self._sync_layers, size=self._sync_layers)

    def set_style(self, font_size=None, shadow_step=None):
        if font_size is not None:
            self._font_size = font_size

        if shadow_step is not None:
            self._shadow_step = shadow_step
            self._shadow_offsets = [
                (0, -self._shadow_step),
                (self._shadow_step, -self._shadow_step),
            ]

        for shadow, offset in zip(self._shadow_layers, self._shadow_offsets):
            shadow.font_size = self._font_size
            shadow._offset = offset

        self._main_title.font_size = self._font_size
        self._sync_layers()

    def _sync_layers(self, *_):
        for shadow in self._shadow_layers:
            dx, dy = shadow._offset
            shadow.pos = (self.x + dx, self.y + dy)
            shadow.size = self.size
            shadow.text_size = self.size

        self._main_title.pos = self.pos
        self._main_title.size = self.size
        self._main_title.text_size = self.size


class AvatarButton(ButtonBehavior, FloatLayout):
    def __init__(self, **kwargs):
        register_game_font()
        super().__init__(size_hint=(None, None), size=(dp(64), dp(64)), **kwargs)
        self._image_inset = dp(2)

        with self.canvas.before:
            self._shadow_color = Color(0, 0, 0, 0)
            self._shadow_rect = Rectangle(pos=self.pos, size=self.size)
            self._bg_color = Color(*COLORS["avatar_placeholder_bg"])
            self._bg_rect = Rectangle(pos=self.pos, size=self.size)
        with self.canvas.after:
            self._border_color = Color(*COLORS["outline"])
            self._border_line = Line(width=1.4, rectangle=(self.x, self.y, self.width, self.height))

        self._image = Image(fit_mode="cover", opacity=0)
        self.add_widget(self._image)

        self._label = Label(
            text="?",
            font_name="GameFont",
            font_size=sp(26),
            color=COLORS["avatar_placeholder_text"],
            halign="center",
            valign="middle",
        )
        self.add_widget(self._label)
        self.bind(pos=self._sync_canvas, size=self._sync_canvas)
        self._image.bind(texture=self._sync_visual_state)

    def _sync_canvas(self, *_):
        self._shadow_rect.pos = self.pos
        self._shadow_rect.size = self.size
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size
        self._border_line.rectangle = (self.x, self.y, self.width, self.height)

        self._image.pos = (self.x + self._image_inset, self.y + self._image_inset)
        self._image.size = (
            max(0, self.width - self._image_inset * 2),
            max(0, self.height - self._image_inset * 2),
        )
        self._label.pos = self.pos
        self._label.size = self.size
        self._label.text_size = self.size

    def on_press(self):
        Animation.cancel_all(self._bg_color)
        Animation(rgba=COLORS["button_pressed"], duration=0.08).start(self._bg_color)

    def on_release(self):
        Animation.cancel_all(self._bg_color)
        Animation(rgba=COLORS["surface_strong"], duration=0.12).start(self._bg_color)

    def _sync_visual_state(self, *_):
        has_texture = self._image.texture is not None and bool(self._image.source)
        self._image.opacity = 1 if has_texture else 0
        self._label.opacity = 0 if has_texture else 1
        self._bg_color.rgba = COLORS["surface_strong"] if has_texture else COLORS["avatar_placeholder_bg"]

    def set_profile(self, profile):
        source = resolve_image_source(getattr(profile, "avatar_source", None) if profile else None)
        self._label.text = "?"
        self._image.source = source or ""
        if source:
            self._image.reload()
        self._sync_visual_state()


class BodyLabel(Label):
    def __init__(self, center=False, **kwargs):
        register_game_font()
        halign = kwargs.pop("halign", "center" if center else "left")
        size_hint_y = kwargs.pop("size_hint_y", None)
        auto_height = kwargs.pop("auto_height", True)
        super().__init__(
            font_name="GameFont",
            color=kwargs.pop("color", COLORS["text_soft"]),
            font_size=kwargs.pop("font_size", sp(15)),
            halign=halign,
            valign=kwargs.pop("valign", "middle"),
            size_hint_y=size_hint_y,
            **kwargs,
        )
        self._auto_height = bool(auto_height)
        self.bind(width=self._sync_text)
        if self._auto_height:
            self.bind(texture_size=self._sync_height)
        self._sync_text()

    def _sync_text(self, *_):
        next_text_size = (max(0, self.width), None)
        if self.text_size != next_text_size:
            self.text_size = next_text_size

    def _sync_height(self, *_):
        next_height = max(dp(22), self.texture_size[1] + dp(4))
        if abs(self.height - next_height) > 0.5:
            self.height = next_height


class PixelLabel(Label):
    def __init__(self, center=False, **kwargs):
        register_game_font()
        halign = kwargs.pop("halign", "center" if center else "left")
        size_hint_y = kwargs.pop("size_hint_y", None)
        auto_height = kwargs.pop("auto_height", True)
        super().__init__(
            font_name="GameFont",
            font_size=kwargs.pop("font_size", sp(16)),
            color=kwargs.pop("color", COLORS["text"]),
            halign=halign,
            valign=kwargs.pop("valign", "middle"),
            size_hint_y=size_hint_y,
            **kwargs,
        )
        self._auto_height = bool(auto_height)
        self.bind(width=self._sync_text)
        if self._auto_height:
            self.bind(texture_size=self._sync_height)
        self._sync_text()

    def _sync_text(self, *_):
        next_text_size = (max(0, self.width), None)
        if self.text_size != next_text_size:
            self.text_size = next_text_size

    def _sync_height(self, *_):
        next_height = max(dp(22), self.texture_size[1] + dp(4))
        if abs(self.height - next_height) > 0.5:
            self.height = next_height


class AliasCoinIcon(Widget):
    def __init__(self, **kwargs):
        super().__init__(size_hint=(None, None), size=(dp(28), dp(28)), **kwargs)
        self._glyph = Label(
            text="AC",
            font_name="BrandFont",
            font_size=sp(11),
            color=(0.35, 0.20, 0.03, 1),
            halign="center",
            valign="middle",
        )
        with self.canvas.before:
            self._shadow_color = Color(0, 0, 0, 0.18)
            self._shadow = Ellipse()
            self._outer_color = Color(0.96, 0.71, 0.10, 1)
            self._outer = Ellipse()
            self._inner_color = Color(1.0, 0.84, 0.22, 1)
            self._inner = Ellipse()
            self._shine_color = Color(1, 1, 1, 0.22)
            self._shine = Ellipse()
            self._border_color = Color(0.69, 0.42, 0.05, 0.95)
            self._border = Line(width=1.1)
        self.add_widget(self._glyph)
        self.bind(pos=self._sync_canvas, size=self._sync_canvas)

    def _sync_canvas(self, *_):
        self._shadow.pos = (self.x, self.y - dp(1.4))
        self._shadow.size = self.size
        self._outer.pos = self.pos
        self._outer.size = self.size
        self._inner.pos = (self.x + dp(2), self.y + dp(2))
        self._inner.size = (max(dp(0), self.width - dp(4)), max(dp(0), self.height - dp(4)))
        self._shine.pos = (self.x + self.width * 0.16, self.y + self.height * 0.56)
        self._shine.size = (self.width * 0.28, self.height * 0.18)
        self._border.ellipse = (self.x, self.y, self.width, self.height)
        self._glyph.pos = self.pos
        self._glyph.size = self.size
        self._glyph.text_size = self.size


class CoinBadge(ButtonBehavior, RoundedPanel):
    def __init__(self, **kwargs):
        size = kwargs.pop("size", (dp(122), dp(52)))
        size_hint = kwargs.pop("size_hint", (None, None))
        super().__init__(
            orientation="horizontal",
            spacing=dp(8),
            padding=[dp(12), dp(8), dp(12), dp(8)],
            size_hint=size_hint,
            size=size,
            bg_color=COLORS["surface"],
            shadow_alpha=0.22,
            **kwargs,
        )
        self._help_popup = None

        self.coin_icon = AliasCoinIcon()
        self.add_widget(self.coin_icon)

        self.coin_value = PixelLabel(text="0", font_size=sp(18), center=False, size_hint_y=None)
        self.add_widget(self.coin_value)
        self.bind(on_release=self._open_help_popup_styled)
        self.bind(on_press=self._animate_press)
        self.bind(on_release=self._animate_release)

    def set_value(self, value):
        self.coin_value.text = str(int(value))

    def refresh_from_session(self):
        app = App.get_running_app()
        is_authenticated = bool(app is not None and getattr(app, "authenticated", False))
        is_guest = bool(app is not None and getattr(app, "guest_mode", False))

        if app is None or not (is_authenticated or is_guest):
            self.opacity = 0
            self.disabled = True
            self.set_value(0)
            return

        coin_value = 0
        if hasattr(app, "current_alias_coins"):
            coin_value = app.current_alias_coins()
        elif is_authenticated and hasattr(app, "current_profile"):
            profile = app.current_profile()
            coin_value = getattr(profile, "alias_coins", 0) if profile is not None else 0
        elif is_guest:
            coin_value = getattr(app, "guest_alias_coins", 0)

        self.opacity = 1
        self.disabled = False
        self.set_value(coin_value)

    def _animate_press(self, *_):
        Animation.cancel_all(self._bg_color)
        Animation(rgba=COLORS["surface_panel"], duration=0.08).start(self._bg_color)

    def _animate_release(self, *_):
        Animation.cancel_all(self._bg_color)
        Animation(rgba=COLORS["surface"], duration=0.12).start(self._bg_color)

    def _open_help_popup(self, *_):
        if self.disabled or self.opacity <= 0.01:
            return

        if self._help_popup is not None:
            self._help_popup.dismiss()
            self._help_popup = None
            return

        body = BoxLayout(orientation="vertical", spacing=dp(10), padding=[dp(14), dp(14), dp(14), dp(14)])
        body.add_widget(
            BodyLabel(
                center=False,
                color=COLORS["text_soft"],
                font_size=sp(13),
                text=(
                    "Как зарабатывать Alias Coin (AC):\n"
                    "• 1 очко в игре = 1 AC\n"
                    "• За правильные ответы и объяснённые слова начисляются очки\n"
                    "• Играй чаще, чтобы накапливать AC\n\n"
                    "Важно:\n"
                    "• Создание комнаты стоит 25 AC\n"
                    "• Первый запуск игры после создания комнаты — бесплатный\n"
                    "• Каждый следующий запуск в том же лобби: -25 AC\n"
                    "• Выход из матча раньше времени: -50 AC и блокировка на 5 минут"
                ),
            )
        )

        close_btn = AppButton(text="Понятно", compact=True, size_hint_y=None, height=dp(42))
        body.add_widget(close_btn)

        popup = Popup(
            title="Памятка Alias Coin",
            title_font="GameFont",
            title_size=sp(18),
            content=body,
            size_hint=(0.9, 0.5),
            auto_dismiss=True,
        )
        self._help_popup = popup

        def _close(*_):
            popup.dismiss()

        close_btn.bind(on_release=_close)
        popup.bind(on_dismiss=lambda *_: setattr(self, "_help_popup", None))
        popup.open()

    def _open_help_popup_styled(self, *_):
        if self.disabled or self.opacity <= 0.01:
            return

        if self._help_popup is not None:
            self._help_popup.dismiss()
            self._help_popup = None
            return

        body = BoxLayout(orientation="vertical", spacing=dp(8), padding=[dp(6), dp(6), dp(6), dp(6)])
        panel = RoundedPanel(
            orientation="vertical",
            spacing=dp(10),
            padding=[dp(16), dp(14), dp(16), dp(14)],
            bg_color=COLORS["surface_card"],
            shadow_alpha=0.24,
        )
        panel._border_color.rgba = (1, 1, 1, 0.16)
        panel._border_line.width = 1.2
        panel.add_widget(PixelLabel(text="Памятка Alias Coin", font_size=sp(18), center=True, size_hint_y=None))
        panel.add_widget(
            BodyLabel(
                center=False,
                color=COLORS["text_soft"],
                font_size=sp(12.5),
                text=(
                    "Как зарабатывать Alias Coin (AC):\n"
                    "• 1 очко в игре = 1 AC\n"
                    "• За правильные ответы и объяснённые слова начисляются очки\n"
                    "• Играй чаще, чтобы накапливать AC\n\n"
                    "Важно:\n"
                    "• Создание комнаты стоит 25 AC\n"
                    "• Первый запуск игры после создания комнаты — бесплатный\n"
                    "• Каждый следующий запуск в том же лобби: -25 AC\n"
                    "• Выход из матча раньше времени: -50 AC и блокировка на 5 минут"
                ),
            )
        )

        close_btn = AppButton(text="Понятно", compact=True, size_hint_y=None, height=dp(42))
        panel.add_widget(close_btn)
        body.add_widget(panel)

        popup = Popup(
            title="",
            separator_height=0,
            content=body,
            size_hint=(0.92, 0.56),
            auto_dismiss=True,
            background="",
            background_color=(0, 0, 0, 0),
        )
        self._help_popup = popup

        def _close(*_):
            popup.dismiss()

        close_btn.bind(on_release=_close)
        popup.bind(on_dismiss=lambda *_: setattr(self, "_help_popup", None))
        popup.open()


class MiniIcon(Widget):
    def __init__(self, icon="users", color=None, **kwargs):
        super().__init__(size_hint=(None, None), size=(dp(16), dp(16)), **kwargs)
        self.icon = (icon or "users").strip().lower()
        self._icon_color_value = color or COLORS["text_muted"]

        with self.canvas.before:
            self._icon_color = Color(*self._icon_color_value)
            self._shape_a = Line(width=dp(1.6))
            self._shape_b = Line(width=dp(1.6))
            self._shape_c = Line(width=dp(1.6))
            self._fill_a = Ellipse()
            self._fill_b = Ellipse()

        self.bind(pos=self._sync_canvas, size=self._sync_canvas)
        self._sync_canvas()

    def set_color(self, color):
        self._icon_color_value = color
        self._icon_color.rgba = color

    def _sync_canvas(self, *_):
        for shape in (self._shape_a, self._shape_b, self._shape_c):
            shape.points = []
            shape.ellipse = (0, 0, 0, 0)
        self._fill_a.size = (0, 0)
        self._fill_b.size = (0, 0)

        if self.icon == "refresh":
            arc_x = self.x + self.width * 0.12
            arc_y = self.y + self.height * 0.12
            arc_w = self.width * 0.76
            arc_h = self.height * 0.76
            self._shape_a.ellipse = (arc_x, arc_y, arc_w, arc_h, 36, 330)
            self._shape_b.points = [
                self.x + self.width * 0.70,
                self.y + self.height * 0.79,
                self.x + self.width * 0.88,
                self.y + self.height * 0.78,
                self.x + self.width * 0.79,
                self.y + self.height * 0.62,
            ]
            return

        if self.icon == "code":
            self._shape_a.points = [
                self.x + self.width * 0.34,
                self.y + self.height * 0.18,
                self.x + self.width * 0.16,
                self.center_y,
                self.x + self.width * 0.34,
                self.y + self.height * 0.82,
            ]
            self._shape_b.points = [
                self.x + self.width * 0.66,
                self.y + self.height * 0.18,
                self.x + self.width * 0.84,
                self.center_y,
                self.x + self.width * 0.66,
                self.y + self.height * 0.82,
            ]
            self._shape_c.points = [
                self.x + self.width * 0.42,
                self.y + self.height * 0.72,
                self.x + self.width * 0.58,
                self.y + self.height * 0.72,
                self.x + self.width * 0.42,
                self.y + self.height * 0.30,
                self.x + self.width * 0.58,
                self.y + self.height * 0.30,
            ]
            return

        if self.icon == "host":
            crown_y = self.y + self.height * 0.62
            self._shape_a.points = [
                self.x + self.width * 0.14,
                crown_y,
                self.x + self.width * 0.30,
                self.y + self.height * 0.82,
                self.x + self.width * 0.50,
                self.y + self.height * 0.52,
                self.x + self.width * 0.70,
                self.y + self.height * 0.82,
                self.x + self.width * 0.86,
                crown_y,
            ]
            self._shape_b.points = [
                self.x + self.width * 0.22,
                self.y + self.height * 0.32,
                self.x + self.width * 0.78,
                self.y + self.height * 0.32,
            ]
            return

        # default: users
        self._shape_a.ellipse = (
            self.x + self.width * 0.14,
            self.y + self.height * 0.50,
            self.width * 0.28,
            self.height * 0.28,
        )
        self._shape_b.ellipse = (
            self.x + self.width * 0.46,
            self.y + self.height * 0.56,
            self.width * 0.22,
            self.height * 0.22,
        )
        self._shape_c.points = [
            self.x + self.width * 0.08,
            self.y + self.height * 0.24,
            self.x + self.width * 0.08,
            self.y + self.height * 0.18,
            self.x + self.width * 0.48,
            self.y + self.height * 0.18,
            self.x + self.width * 0.48,
            self.y + self.height * 0.24,
            self.x + self.width * 0.72,
            self.y + self.height * 0.24,
            self.x + self.width * 0.72,
            self.y + self.height * 0.18,
            self.x + self.width * 0.92,
            self.y + self.height * 0.18,
            self.x + self.width * 0.92,
            self.y + self.height * 0.24,
        ]


class IconMetaChip(RoundedPanel):
    def __init__(self, icon="users", text="", **kwargs):
        chip_width = kwargs.pop("width", dp(92))
        super().__init__(
            orientation="horizontal",
            spacing=dp(6),
            padding=[dp(10), dp(6), dp(10), dp(6)],
            size_hint=(None, None),
            width=chip_width,
            height=dp(30),
            bg_color=COLORS["surface_chip"],
            shadow_alpha=0.08,
            **kwargs,
        )
        self._border_color.rgba = COLORS["outline_soft"]
        self._border_line.width = 1.0
        self.icon = MiniIcon(icon=icon, color=COLORS["text_muted"])
        self.add_widget(self.icon)
        self.label = BodyLabel(
            text=text,
            font_size=sp(10.5),
            color=COLORS["text_soft"],
            size_hint=(1, 1),
            auto_height=False,
        )
        self.label.halign = "left"
        self.label.bind(size=self._sync_label_text)
        self.add_widget(self.label)
        self._sync_label_text()

    def set_text(self, text):
        self.label.text = text

    def _sync_label_text(self, *_):
        next_size = (max(0, self.label.width), None)
        if self.label.text_size != next_size:
            self.label.text_size = next_size


class IconCircleButton(ButtonBehavior, FloatLayout):
    def __init__(self, icon="refresh", **kwargs):
        button_size = kwargs.pop("size", (dp(38), dp(38)))
        super().__init__(size_hint=(None, None), size=button_size, **kwargs)
        self.icon_name = icon
        self._spin_event = None
        self._spin_speed = 420.0
        self._spun_degrees = 0.0
        self._stop_requested = False

        with self.canvas.before:
            self._shadow_color = Color(0, 0, 0, 0.14)
            self._shadow = Ellipse()
            self._bg_color = Color(*COLORS["surface_card"])
            self._bg = Ellipse()
            self._border_color = Color(*COLORS["outline_soft"])
            self._border = Line(width=1.1)
            self._push_matrix = PushMatrix()
            self._rotation = Rotate(angle=0, origin=self.center)

        self.icon = MiniIcon(icon=icon, color=COLORS["text"])
        self.add_widget(self.icon)

        with self.canvas.after:
            self._pop_matrix = PopMatrix()

        self.bind(pos=self._sync_canvas, size=self._sync_canvas)
        self._sync_canvas()

    def _sync_canvas(self, *_):
        self._shadow.pos = (self.x, self.y - dp(1.5))
        self._shadow.size = self.size
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._border.ellipse = (self.x, self.y, self.width, self.height)
        self._rotation.origin = self.center
        self.icon.pos = (
            self.center_x - self.icon.width / 2,
            self.center_y - self.icon.height / 2,
        )

    def on_press(self):
        if self.disabled:
            return
        trigger_tap_feedback(play_sound=True, haptic=False)
        Animation.cancel_all(self._bg_color)
        Animation(rgba=COLORS["surface_panel"], duration=0.08).start(self._bg_color)

    def on_release(self):
        if self._spin_event is None:
            Animation.cancel_all(self._bg_color)
            Animation(rgba=COLORS["surface_card"], duration=0.12).start(self._bg_color)

    def start_spinning(self):
        Animation.cancel_all(self._rotation)
        Animation.cancel_all(self._bg_color)
        self._spun_degrees = 0.0
        self._stop_requested = False
        if self._spin_event is None:
            self._spin_event = Clock.schedule_interval(self._advance_spin, 1 / 60)
        Animation(rgba=COLORS["surface_panel"], duration=0.10).start(self._bg_color)

    def stop_spinning(self):
        if self._spin_event is None:
            Animation.cancel_all(self._bg_color)
            Animation(rgba=COLORS["surface_card"], duration=0.12).start(self._bg_color)
            return

        # Guarantee at least one full revolution per refresh click.
        if self._spun_degrees < 360:
            self._stop_requested = True
            return

        self._finalize_spin()

    def _finalize_spin(self):
        if self._spin_event is not None:
            self._spin_event.cancel()
            self._spin_event = None
        self._stop_requested = False
        Animation.cancel_all(self._rotation)
        current_angle = self._rotation.angle % 360
        remaining = 360 - current_angle
        if remaining < 1.0:
            remaining = 360.0
        target_angle = self._rotation.angle + remaining
        settle_duration = max(0.14, remaining / self._spin_speed)
        Animation(angle=target_angle, duration=settle_duration, t="out_quad").start(self._rotation)
        Animation.cancel_all(self._bg_color)
        Animation(rgba=COLORS["surface_card"], duration=0.12).start(self._bg_color)

    def _advance_spin(self, dt):
        rotated = dt * self._spin_speed
        self._rotation.angle = (self._rotation.angle - rotated) % 360
        self._spun_degrees += rotated
        if self._stop_requested and self._spun_degrees >= 360:
            self._finalize_spin()


class LoadingOverlay(FloatLayout):
    def __init__(self, **kwargs):
        kwargs.setdefault("size_hint", (1, 1))
        super().__init__(**kwargs)
        self._shown_size_hint = tuple(self.size_hint or (1, 1))
        self.opacity = 0
        self.disabled = True
        self._spin_event = None
        self._angle = 0.0

        with self.canvas.before:
            self._dim_color = Color(0.03, 0.07, 0.12, 0.54)
            self._dim_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._sync_dim, size=self._sync_dim)

        self.panel = RoundedPanel(
            orientation="vertical",
            spacing=dp(10),
            padding=[dp(16), dp(14), dp(16), dp(14)],
            size_hint=(None, None),
            size=(dp(250), dp(118)),
            pos_hint={"center_x": 0.5, "center_y": 0.5},
            bg_color=COLORS["surface_panel"],
            shadow_alpha=0.22,
        )
        self.panel.bind(pos=lambda *_: self._center_spinner(), size=lambda *_: self._center_spinner())

        spinner_wrap = FloatLayout(size_hint=(1, None), height=dp(40))
        self._spinner = Widget(size_hint=(None, None), size=(dp(30), dp(30)))
        with self._spinner.canvas.before:
            self._spinner_color = Color(*COLORS["accent"])
            self._spinner_push = PushMatrix()
            self._spinner_rotate = Rotate(angle=0, origin=self._spinner.center)
            self._spinner_arc = Line(width=dp(2.4), ellipse=(0, 0, 0, 0, 30, 300))
            self._spinner_pop = PopMatrix()
        self._spinner.bind(pos=self._sync_spinner, size=self._sync_spinner)
        spinner_wrap.add_widget(self._spinner)
        self.panel.add_widget(spinner_wrap)

        self.message_label = BodyLabel(
            center=True,
            color=COLORS["text_soft"],
            font_size=sp(12.5),
            text="Загрузка...",
            size_hint_y=None,
        )
        self.panel.add_widget(self.message_label)
        self.add_widget(self.panel)
        Clock.schedule_once(lambda *_: self._center_spinner(), 0)

    def _sync_dim(self, *_):
        self._dim_rect.pos = self.pos
        self._dim_rect.size = self.size

    def _center_spinner(self):
        self._spinner.pos = (
            self.panel.center_x - self._spinner.width / 2,
            self.panel.y + self.panel.height - dp(50),
        )
        self._sync_spinner()

    def _sync_spinner(self, *_):
        self._spinner_rotate.origin = self._spinner.center
        self._spinner_arc.ellipse = (
            self._spinner.x,
            self._spinner.y,
            self._spinner.width,
            self._spinner.height,
            30,
            300,
        )

    def _advance(self, dt):
        self._angle = (self._angle - dt * 420.0) % 360
        self._spinner_rotate.angle = self._angle
        return True

    def show(self, message="Загрузка..."):
        print(f"[LOADING_OVERLAY] SHOW: {message}")
        self.message_label.text = message
        self.size_hint = self._shown_size_hint
        self.disabled = False
        self.opacity = 1
        self._angle = 0.0
        self._spinner_rotate.angle = 0
        self._center_spinner()
        if self._spin_event is None:
            self._spin_event = Clock.schedule_interval(self._advance, 1 / 60.0)

    def hide(self):
        print(f"[LOADING_OVERLAY] HIDE")
        if self._spin_event is not None:
            self._spin_event.cancel()
            self._spin_event = None
        self.opacity = 0
        self.disabled = True
        self.size_hint = (None, None)
        self.size = (0, 0)

    def _is_interactive(self):
        return self.opacity > 0.01 and not self.disabled

    def on_touch_down(self, touch):
        if not self._is_interactive():
            return False
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if not self._is_interactive():
            return False
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if not self._is_interactive():
            return False
        return super().on_touch_up(touch)


def build_scrollable_content(padding=None, spacing=16):
    scroll = ScrollView(do_scroll_x=False, bar_width=dp(4), scroll_type=["bars", "content"])
    content = BoxLayout(
        orientation="vertical",
        size_hint_y=None,
        spacing=dp(spacing),
        padding=padding or [dp(20), dp(34), dp(20), dp(24)],
    )
    content.bind(minimum_height=content.setter("height"))
    scroll.add_widget(content)
    return scroll, content


def spacer(height):
    return Widget(size_hint_y=None, height=dp(height))
