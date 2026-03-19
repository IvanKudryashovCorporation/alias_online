from pathlib import Path

from kivy.animation import Animation
from kivy.app import App
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
    def __init__(self, variant="lobby", **kwargs):
        super().__init__(**kwargs)
        self.variant = (variant or "lobby").strip().lower()

        self._background_image = Image(source=str(BACKGROUND_PATH), fit_mode="fill")
        self.add_widget(self._background_image)

        self._scene = Widget()
        with self._scene.canvas.before:
            if self.variant == "game":
                self._scene_shadow_color = Color(0.03, 0.08, 0.12, 0.22)
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

        self._scene_shadow.pos = (x, y)
        self._scene_shadow.size = (width, height * 0.34)

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
        self.text_size = (max(0, self.width), None)

    def _sync_height(self, *_):
        self.height = max(dp(22), self.texture_size[1] + dp(4))


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
        self.text_size = (max(0, self.width), None)

    def _sync_height(self, *_):
        self.height = max(dp(22), self.texture_size[1] + dp(4))


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


class CoinBadge(RoundedPanel):
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
        self.coin_icon = AliasCoinIcon()
        self.add_widget(self.coin_icon)

        self.coin_value = PixelLabel(text="0", font_size=sp(18), center=False, size_hint_y=None)
        self.add_widget(self.coin_value)

    def set_value(self, value):
        self.coin_value.text = str(int(value))

    def refresh_from_session(self):
        app = App.get_running_app()
        profile = app.current_profile() if app is not None and hasattr(app, "current_profile") else None
        self.set_value(getattr(profile, "alias_coins", 0) if profile is not None else 0)


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
        super().__init__(
            orientation="horizontal",
            spacing=dp(6),
            padding=[dp(10), dp(6), dp(10), dp(6)],
            size_hint=(None, None),
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
            size_hint=(None, 1),
            auto_height=False,
        )
        self.label.bind(texture_size=self._sync_label_width)
        self.add_widget(self.label)
        self.bind(minimum_width=self.setter("width"))
        self._sync_label_width()

    def set_text(self, text):
        self.label.text = text

    def _sync_label_width(self, *_):
        self.label.width = max(dp(18), self.label.texture_size[0] + dp(2))


class IconCircleButton(ButtonBehavior, FloatLayout):
    def __init__(self, icon="refresh", **kwargs):
        button_size = kwargs.pop("size", (dp(38), dp(38)))
        super().__init__(size_hint=(None, None), size=button_size, **kwargs)
        self.icon_name = icon

        with self.canvas.before:
            self._shadow_color = Color(0, 0, 0, 0.14)
            self._shadow = Ellipse()
            self._bg_color = Color(*COLORS["surface_card"])
            self._bg = Ellipse()
            self._border_color = Color(*COLORS["outline_soft"])
            self._border = Line(width=1.1)

        self.icon = MiniIcon(icon=icon, color=COLORS["text"])
        self.add_widget(self.icon)
        self.bind(pos=self._sync_canvas, size=self._sync_canvas)
        self._sync_canvas()

    def _sync_canvas(self, *_):
        self._shadow.pos = (self.x, self.y - dp(1.5))
        self._shadow.size = self.size
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._border.ellipse = (self.x, self.y, self.width, self.height)
        self.icon.pos = (
            self.center_x - self.icon.width / 2,
            self.center_y - self.icon.height / 2,
        )

    def on_press(self):
        Animation.cancel_all(self._bg_color)
        Animation(rgba=COLORS["surface_panel"], duration=0.08).start(self._bg_color)

    def on_release(self):
        Animation.cancel_all(self._bg_color)
        Animation(rgba=COLORS["surface_card"], duration=0.12).start(self._bg_color)


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
