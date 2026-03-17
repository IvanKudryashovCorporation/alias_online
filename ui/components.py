from pathlib import Path

from kivy.animation import Animation
from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle, Triangle
from kivy.metrics import dp, sp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

from .theme import BACKGROUND_PATH, COLORS, radius, register_game_font


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
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.add_widget(Image(source=str(BACKGROUND_PATH), fit_mode="fill"))

        self._scene = Widget()
        with self._scene.canvas.before:
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
            self._overlay_color = Color(*COLORS["overlay"])
            self._overlay_rect = Rectangle(pos=self._overlay.pos, size=self._overlay.size)
        self._overlay.bind(pos=self._sync_overlay, size=self._sync_overlay)
        self.add_widget(self._overlay)

    def _sync_overlay(self, *_):
        self._overlay_rect.pos = self._overlay.pos
        self._overlay_rect.size = self._overlay.size

    def _sync_scene(self, *_):
        width = self._scene.width
        height = self._scene.height
        x = self._scene.x
        y = self._scene.y

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
        Animation.cancel_all(self._button_color)
        Animation(rgba=self._pressed_button_color, duration=0.08).start(self._button_color)

    def on_release(self):
        Animation.cancel_all(self._button_color)
        Animation(rgba=self._rest_button_color, duration=0.12).start(self._button_color)


class AppTextInput(TextInput):
    def __init__(self, **kwargs):
        register_game_font()
        multiline = kwargs.pop("multiline", False)
        height = kwargs.pop("height", dp(60 if not multiline else 144))
        self._rendering_hint_label = False
        super().__init__(
            multiline=multiline,
            font_name="GameFont",
            font_size=sp(16),
            size_hint_y=None,
            height=height,
            padding=[dp(16), dp(18), dp(16), dp(12)],
            background_normal="",
            background_active="",
            background_color=COLORS["input_bg"],
            foreground_color=COLORS["input_text"],
            disabled_foreground_color=COLORS["input_text"],
            hint_text_color=(0.29, 0.32, 0.38, 1),
            cursor_color=COLORS["input_text"],
            selection_color=(0.18, 0.22, 0.3, 0.22),
            use_bubble=False,
            use_handles=False,
            write_tab=False,
            **kwargs,
        )

        self._corner_radius = dp(18)

        with self.canvas.before:
            self._bg_color = Color(*COLORS["input_bg"])
            self._bg_rect = RoundedRectangle(radius=radius(18))
            self._border_color = Color(*COLORS["outline"])
            self._border_line = Line(width=1.1)

        self.bind(pos=self._sync_canvas, size=self._sync_canvas)
        self.bind(
            background_color=self._apply_surface_palette,
            foreground_color=self._refresh_text_colors,
            disabled_foreground_color=self._refresh_text_colors,
            hint_text_color=self._refresh_text_colors,
            disabled=self._refresh_text_colors,
        )
        self.bind(readonly=self._apply_surface_palette)
        self.bind(readonly=self._refresh_text_colors)
        self._apply_surface_palette()
        self._refresh_text_colors()

    def _apply_surface_palette(self, *_):
        if self.readonly:
            bg_color = COLORS["input_readonly_bg"]
            border_color = COLORS["input_readonly_outline"]
            cursor_color = (0, 0, 0, 0)
        else:
            bg_color = COLORS["input_bg"]
            border_color = COLORS["outline"]
            cursor_color = COLORS["input_text"]

        self.background_color = bg_color
        self.cursor_color = cursor_color
        self._bg_color.rgba = bg_color
        self._border_color.rgba = border_color

    def _resolve_line_color(self):
        if self._rendering_hint_label:
            return tuple(self.hint_text_color)
        if self.disabled:
            return tuple(self.disabled_foreground_color)
        return tuple(self.foreground_color)

    def _get_line_options(self):
        line_options = super()._get_line_options().copy()
        line_options["color"] = self._resolve_line_color()
        return line_options

    def _create_line_label(self, text, hint=False):
        self._rendering_hint_label = hint
        try:
            return super()._create_line_label(text, hint=hint)
        finally:
            self._rendering_hint_label = False

    def _refresh_text_colors(self, *_):
        text_color = COLORS["input_readonly_text"] if self.readonly else COLORS["input_text"]
        self.foreground_color = text_color
        self.disabled_foreground_color = text_color
        self.cursor_color = (0, 0, 0, 0) if self.readonly else COLORS["input_text"]
        self._trigger_refresh_text()
        self._refresh_hint_text()

    def _sync_canvas(self, *_):
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size
        self._border_line.rounded_rectangle = (self.x, self.y, self.width, self.height, self._corner_radius)


class BrandTitle(Widget):
    def __init__(self, text="ALIAS\nONLINE", font_size=None, shadow_step=None, layers=None, **kwargs):
        register_game_font()
        height = kwargs.pop("height", dp(320))
        super().__init__(size_hint_y=None, height=height, **kwargs)

        font_size = font_size or sp(62)
        shadow_step = shadow_step or dp(4)
        layers = layers or [
            (0, -shadow_step),
            (shadow_step, -shadow_step),
        ]

        self._shadow_layers = []
        for dx, dy in layers:
            shadow = Label(
                text=text,
                font_name="BrandFont",
                font_size=font_size,
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
            font_size=font_size,
            color=COLORS["accent"],
            halign="center",
            valign="middle",
        )
        self.add_widget(self._main_title)
        self.bind(pos=self._sync_layers, size=self._sync_layers)

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

    def set_profile(self, profile):
        source = resolve_image_source(getattr(profile, "avatar_source", None) if profile else None)
        self._label.text = "?"
        self._image.source = source or ""
        if source:
            self._image.reload()
        self._image.opacity = 1 if source else 0
        self._label.opacity = 0 if source else 1
        self._bg_color.rgba = COLORS["surface_strong"] if source else COLORS["avatar_placeholder_bg"]


class BodyLabel(Label):
    def __init__(self, center=False, **kwargs):
        register_game_font()
        halign = kwargs.pop("halign", "center" if center else "left")
        size_hint_y = kwargs.pop("size_hint_y", None)
        super().__init__(
            font_name="GameFont",
            color=kwargs.pop("color", COLORS["text_soft"]),
            font_size=kwargs.pop("font_size", sp(15)),
            halign=halign,
            valign=kwargs.pop("valign", "middle"),
            size_hint_y=size_hint_y,
            **kwargs,
        )
        self.bind(width=self._sync_text, texture_size=self._sync_height)

    def _sync_text(self, *_):
        self.text_size = (max(0, self.width), None)

    def _sync_height(self, *_):
        self.height = max(dp(22), self.texture_size[1] + dp(4))


class PixelLabel(Label):
    def __init__(self, center=False, **kwargs):
        register_game_font()
        halign = kwargs.pop("halign", "center" if center else "left")
        size_hint_y = kwargs.pop("size_hint_y", None)
        super().__init__(
            font_name="GameFont",
            font_size=kwargs.pop("font_size", sp(16)),
            color=kwargs.pop("color", COLORS["text"]),
            halign=halign,
            valign=kwargs.pop("valign", "middle"),
            size_hint_y=size_hint_y,
            **kwargs,
        )
        self.bind(width=self._sync_text, texture_size=self._sync_height)

    def _sync_text(self, *_):
        self.text_size = (max(0, self.width), None)

    def _sync_height(self, *_):
        self.height = max(dp(22), self.texture_size[1] + dp(4))


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
