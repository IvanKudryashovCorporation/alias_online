from datetime import datetime
from pathlib import Path

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from services import begin_registration_verification, change_profile_password, update_profile
from ui import AppButton, AppTextInput, BodyLabel, BrandTitle, CoinBadge, COLORS, PixelLabel, RoundedPanel, ScreenBackground, register_game_font, resolve_image_source


class SubtleActionButton(ButtonBehavior, Label):
    def __init__(self, text="", **kwargs):
        register_game_font()
        text_color = kwargs.pop("text_color", COLORS["text_muted"])
        idle_opacity = kwargs.pop("idle_opacity", 0.85)
        pressed_opacity = kwargs.pop("pressed_opacity", 0.55)
        super().__init__(size_hint_y=None, height=dp(22), **kwargs)
        self.text = text
        self.font_name = "GameFont"
        self.font_size = sp(12)
        self.color = text_color
        self.halign = "center"
        self.valign = "middle"
        self.idle_opacity = idle_opacity
        self.pressed_opacity = pressed_opacity
        self.opacity = self.idle_opacity
        self.bind(size=self._sync_text)

    def _sync_text(self, *_):
        self.text_size = self.size

    def on_press(self):
        self.opacity = self.pressed_opacity

    def on_release(self):
        self.opacity = self.idle_opacity


class AvatarPreview(FloatLayout):
    def __init__(self, **kwargs):
        register_game_font()
        super().__init__(
            size_hint=(None, None),
            size=(dp(88), dp(88)),
            **kwargs,
        )

        from kivy.graphics import Color, Line, Rectangle

        with self.canvas.before:
            self._bg_color = Color(*COLORS["avatar_placeholder_bg"])
            self._bg_rect = Rectangle(pos=self.pos, size=self.size)
            self._border_color = Color(*COLORS["outline"])
            self._border_line = Line(width=1.2, rectangle=(self.x, self.y, self.width, self.height))

        self._image = Image(fit_mode="cover", opacity=0)
        self.add_widget(self._image)

        self._placeholder = PixelLabel(
            text="?",
            font_size=sp(22),
            color=COLORS["avatar_placeholder_text"],
            center=True,
        )
        self.add_widget(self._placeholder)

        self.bind(pos=self._sync_children, size=self._sync_children)
        self._image.bind(texture=self._sync_visual_state)

    def _sync_children(self, *_):
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size
        self._border_line.rectangle = (self.x, self.y, self.width, self.height)

        self._image.pos = (self.x + dp(2), self.y + dp(2))
        self._image.size = (self.width - dp(4), self.height - dp(4))
        self._placeholder.pos = self.pos
        self._placeholder.size = self.size
        self._placeholder.text_size = self.size

    def _sync_visual_state(self, *_):
        has_texture = self._image.texture is not None and bool(self._image.source)
        self._image.opacity = 1 if has_texture else 0
        self._placeholder.opacity = 0 if has_texture else 1
        self._bg_color.rgba = COLORS["surface_strong"] if has_texture else COLORS["avatar_placeholder_bg"]

    def set_avatar(self, source=None):
        resolved_source = resolve_image_source(source)
        self._image.source = resolved_source or ""
        if resolved_source:
            self._image.reload()
        self._sync_visual_state()


class ProfileStatCard(RoundedPanel):
    def __init__(self, title="", **kwargs):
        super().__init__(
            bg_color=COLORS["surface_panel"],
            shadow_alpha=0.12,
            orientation="vertical",
            spacing=dp(1),
            padding=[dp(8), dp(6), dp(8), dp(6)],
            size_hint=(None, None),
            size=(dp(126), dp(52)),
            **kwargs,
        )
        self.title_label = BodyLabel(center=True, color=COLORS["text_muted"], font_size=sp(9.5), text=title)
        self.value_label = PixelLabel(center=True, font_size=sp(15), text="0")
        self.add_widget(self.title_label)
        self.add_widget(self.value_label)

    def set_value(self, value):
        self.value_label.text = str(value)


class RegistrationScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        register_game_font()
        self.selected_avatar_path = None
        self.avatar_picker_popup = None
        self.change_password_popup = None
        self.profile_mode = False
        self.default_content_spacing = dp(10)
        self.compact_content_spacing = dp(6)
        self.default_content_padding = [dp(18), dp(16), dp(18), dp(18)]
        self.compact_content_padding = [dp(12), dp(12), dp(12), dp(8)]
        self.default_card_padding = [dp(16), dp(14), dp(16), dp(14)]
        self.compact_card_padding = [dp(18), dp(16), dp(18), dp(12)]
        self.default_card_spacing = dp(10)
        self.compact_card_spacing = dp(6)
        self.default_input_padding = [dp(16), dp(14), dp(16), dp(14)]
        self.profile_input_padding = [dp(14), dp(11), dp(14), dp(11)]
        self.field_width = dp(276)
        self.button_width = dp(274)
        self.avatar_panel_width = dp(214)

        root = ScreenBackground()

        self.scroll = ScrollView(
            do_scroll_x=False,
            do_scroll_y=True,
            bar_width=dp(4),
            scroll_type=["bars", "content"],
        )

        content = BoxLayout(
            orientation="vertical",
            spacing=self.default_content_spacing,
            padding=self.default_content_padding,
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))
        self.content = content

        top_bar = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(44))
        self.back_btn = AppButton(text="\u041d\u0430\u0437\u0430\u0434", compact=True, size_hint=(None, None), size=(dp(128), dp(42)))
        self.back_btn.bind(on_release=self._go_back)
        top_bar.add_widget(self.back_btn)
        top_bar.add_widget(Widget())
        content.add_widget(top_bar)

        self.brand_title = BrandTitle(text="ALIAS ONLINE", height=dp(148), font_size=sp(50), shadow_step=dp(3))
        content.add_widget(self.brand_title)

        self.profile_header = BoxLayout(
            orientation="vertical",
            spacing=dp(2),
            size_hint_y=None,
            height=0,
            opacity=0,
        )
        self.profile_title = PixelLabel(
            text="\u041f\u0440\u043e\u0444\u0438\u043b\u044c",
            font_size=sp(16),
            center=True,
            size_hint_y=None,
        )
        self.profile_summary = BodyLabel(
            center=True,
            color=COLORS["text_muted"],
            font_size=sp(10),
            size_hint_y=None,
            text="",
        )
        self.profile_header.add_widget(self.profile_title)
        self.profile_header.add_widget(self.profile_summary)
        content.add_widget(self.profile_header)

        self.top_spacer = Widget(size_hint_y=None, height=dp(10))
        content.add_widget(self.top_spacer)

        self.card = RoundedPanel(
            bg_color=COLORS["surface_card"],
            shadow_alpha=0.28,
            orientation="vertical",
            padding=self.default_card_padding,
            spacing=self.default_card_spacing,
            size_hint_y=None,
            height=dp(560),
        )
        self.card._border_color.rgba = (1, 1, 1, 0.16)
        self.card._border_line.width = 1.2
        self.card.pos_hint = {"center_x": 0.5}

        self.title_label = PixelLabel(text="\u0420\u0435\u0433\u0438\u0441\u0442\u0440\u0430\u0446\u0438\u044f", font_size=sp(18), center=True, size_hint_y=None)
        self.title_label.height = dp(28)
        self.card.add_widget(self.title_label)

        self.subtitle_row = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(32))
        self.subtitle_label = BodyLabel(
            center=True,
            color=COLORS["text_muted"],
            font_size=sp(12),
            text="\u0421\u043e\u0437\u0434\u0430\u0439 \u043f\u0440\u043e\u0444\u0438\u043b\u044c, \u0447\u0442\u043e\u0431\u044b \u0432\u043e\u0439\u0442\u0438 \u0432 \u0438\u0433\u0440\u0443.",
        )
        self.subtitle_row.add_widget(self.subtitle_label)
        self.card.add_widget(self.subtitle_row)

        self.name_input = AppTextInput(hint_text="\u0418\u043c\u044f", height=dp(48))
        self.email_input = AppTextInput(hint_text="E-mail", height=dp(48))
        self.password_input = AppTextInput(hint_text="\u041f\u0430\u0440\u043e\u043b\u044c", password=True, height=dp(48))
        self.confirm_password_input = AppTextInput(hint_text="\u041f\u043e\u0434\u0442\u0432\u0435\u0440\u0434\u0438 \u043f\u0430\u0440\u043e\u043b\u044c", password=True, height=dp(48))
        self.name_input.padding = self.default_input_padding[:]
        self.email_input.padding = self.default_input_padding[:]
        self.password_input.padding = self.default_input_padding[:]
        self.confirm_password_input.padding = self.default_input_padding[:]

        self.name_caption_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=0, opacity=0)
        self.name_caption = BodyLabel(
            text="\u041d\u0438\u043a\u043d\u0435\u0439\u043c",
            color=COLORS["text_muted"],
            font_size=sp(11),
            size_hint_y=None,
        )
        self.name_caption.size_hint_x = None
        self.name_caption.width = self.field_width
        self.name_caption.halign = "left"
        self.name_caption_row.add_widget(Widget())
        self.name_caption_row.add_widget(self.name_caption)
        self.name_caption_row.add_widget(Widget())

        self.email_caption_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=0, opacity=0)
        self.email_caption = BodyLabel(
            text="E-mail",
            color=COLORS["text_muted"],
            font_size=sp(11),
            size_hint_y=None,
        )
        self.email_caption.size_hint_x = None
        self.email_caption.width = self.field_width
        self.email_caption.halign = "left"
        self.email_caption_row.add_widget(Widget())
        self.email_caption_row.add_widget(self.email_caption)
        self.email_caption_row.add_widget(Widget())

        self.name_row = self._centered_row(self.name_input, height=dp(48), width=self.field_width)
        self.email_row = self._centered_row(self.email_input, height=dp(48), width=self.field_width)
        self.password_row = self._centered_row(self.password_input, height=dp(48), width=self.field_width)
        self.confirm_password_row = self._centered_row(self.confirm_password_input, height=dp(48), width=self.field_width)
        self.card.add_widget(self.name_caption_row)
        self.card.add_widget(self.name_row)
        self.card.add_widget(self.email_caption_row)
        self.card.add_widget(self.email_row)
        self.card.add_widget(self.password_row)
        self.card.add_widget(self.confirm_password_row)

        self.stats_wrap = BoxLayout(
            orientation="vertical",
            spacing=dp(6),
            size_hint_y=None,
            height=0,
            opacity=0,
        )
        stats_row_one = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(52))
        stats_row_one.add_widget(Widget())
        self.coins_stat = ProfileStatCard(title="Игр")
        self.games_stat = ProfileStatCard(title="Заработано")
        stats_row_one.add_widget(self.coins_stat)
        stats_row_one.add_widget(self.games_stat)
        stats_row_one.add_widget(Widget())
        self.stats_wrap.add_widget(stats_row_one)

        stats_row_two = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(52))
        stats_row_two.add_widget(Widget())
        self.points_stat = ProfileStatCard(title="Угадано")
        self.rooms_stat = ProfileStatCard(title="Объяснено")
        stats_row_two.add_widget(self.points_stat)
        stats_row_two.add_widget(self.rooms_stat)
        stats_row_two.add_widget(Widget())
        self.stats_wrap.add_widget(stats_row_two)
        self.card.add_widget(self.stats_wrap)

        self.avatar_mode_note_row = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(22))
        self.avatar_mode_note = BodyLabel(
            center=True,
            color=COLORS["text_muted"],
            font_size=sp(11),
            text="\u0414\u043e\u0431\u0430\u0432\u044c \u0444\u043e\u0442\u043e \u0441\u0440\u0430\u0437\u0443 \u0438\u043b\u0438 \u0441\u0434\u0435\u043b\u0430\u0439 \u044d\u0442\u043e \u043f\u043e\u0437\u0436\u0435 \u0432 \u043f\u0440\u043e\u0444\u0438\u043b\u0435.",
        )
        self.avatar_mode_note_row.add_widget(self.avatar_mode_note)
        self.card.add_widget(self.avatar_mode_note_row)

        self.avatar_section = RoundedPanel(
            bg_color=COLORS["surface_panel"],
            shadow_alpha=0.16,
            orientation="vertical",
            spacing=dp(8),
            padding=[dp(14), dp(12), dp(14), dp(12)],
            size_hint=(None, None),
            width=self.avatar_panel_width,
            height=0,
            opacity=0,
        )
        self.avatar_section_row = self._centered_row(self.avatar_section, height=0)

        self.preview_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(92))
        self.avatar_preview = AvatarPreview()
        self.preview_row.add_widget(Widget())
        self.preview_row.add_widget(self.avatar_preview)
        self.preview_row.add_widget(Widget())
        self.avatar_section.add_widget(self.preview_row)

        self.avatar_button_gap = Widget(size_hint_y=None, height=dp(12))
        self.avatar_section.add_widget(self.avatar_button_gap)

        self.add_photo_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(42))
        self.add_photo_row.add_widget(Widget())
        self.pick_avatar_btn = AppButton(
            text="\u0417\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044c \u0444\u043e\u0442\u043e",
            compact=True,
            font_size=sp(13),
            size_hint=(None, None),
            size=(dp(210), dp(40)),
        )
        self.pick_avatar_btn.bind(on_release=self.open_avatar_picker)
        self.add_photo_row.add_widget(self.pick_avatar_btn)
        self.add_photo_row.add_widget(Widget())
        self.avatar_section.add_widget(self.add_photo_row)

        self.clear_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=0)
        self.clear_row.add_widget(Widget())
        self.clear_avatar_btn = SubtleActionButton(text="\u0423\u0431\u0440\u0430\u0442\u044c \u0444\u043e\u0442\u043e")
        self.clear_avatar_btn.bind(on_release=self.clear_avatar)
        self.clear_row.add_widget(self.clear_avatar_btn)
        self.clear_row.add_widget(Widget())
        self.avatar_section.add_widget(self.clear_row)

        self.avatar_status_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=0, opacity=0)
        self.avatar_status_label = BodyLabel(
            center=True,
            color=COLORS["text_muted"],
            font_size=sp(11),
            shorten=True,
            shorten_from="center",
            text="",
        )
        self.avatar_status_row.add_widget(self.avatar_status_label)
        self.avatar_section.add_widget(self.avatar_status_row)
        self.card.add_widget(self.avatar_section_row)

        self.bio_input = AppTextInput(
            hint_text="\u041e\u043f\u0438\u0441\u0430\u043d\u0438\u0435 \u043f\u0440\u043e\u0444\u0438\u043b\u044f (\u043d\u0435\u043e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u044c\u043d\u043e)",
            multiline=True,
            height=dp(72),
        )
        self.bio_row = self._centered_row(self.bio_input, height=dp(72), width=self.field_width)
        self.card.add_widget(self.bio_row)

        self.password_panel = RoundedPanel(
            bg_color=COLORS["surface_panel"],
            shadow_alpha=0.14,
            orientation="vertical",
            spacing=dp(6),
            padding=[dp(12), dp(10), dp(12), dp(10)],
            size_hint=(None, None),
            width=self.field_width,
            height=0,
            opacity=0,
        )
        self.password_panel_row = self._centered_row(self.password_panel, height=0, width=self.field_width)
        self.password_panel_title = BodyLabel(
            center=True,
            color=COLORS["text_muted"],
            font_size=sp(11.5),
            size_hint_y=None,
            height=dp(20),
            text="Изменить пароль",
        )
        self.password_panel.add_widget(self.password_panel_title)
        self.current_password_input = AppTextInput(hint_text="Текущий пароль", password=True, height=dp(42))
        self.new_password_input = AppTextInput(hint_text="Новый пароль", password=True, height=dp(42))
        self.current_password_input.height = 0
        self.current_password_input.opacity = 0
        self.current_password_input.disabled = True
        self.new_password_input.height = 0
        self.new_password_input.opacity = 0
        self.new_password_input.disabled = True
        self.password_panel.add_widget(self.current_password_input)
        self.password_panel.add_widget(self.new_password_input)

        self.change_password_btn_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(36))
        self.change_password_btn_row.add_widget(Widget())
        self.change_password_btn = AppButton(
            text="Изменить пароль",
            compact=True,
            font_size=sp(13),
            size_hint=(None, None),
            size=(dp(186), dp(34)),
        )
        self.change_password_btn.bind(on_release=self.open_change_password_dialog)
        self.change_password_btn_row.add_widget(self.change_password_btn)
        self.change_password_btn_row.add_widget(Widget())
        self.password_panel.add_widget(self.change_password_btn_row)

        self.profile_forgot_btn_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(24))
        self.profile_forgot_btn_row.add_widget(Widget())
        self.profile_forgot_btn = SubtleActionButton(text="Забыл пароль?")
        self.profile_forgot_btn.size_hint = (None, None)
        self.profile_forgot_btn.size = (dp(176), dp(22))
        self.profile_forgot_btn.color = COLORS["text_soft"]
        self.profile_forgot_btn.idle_opacity = 1
        self.profile_forgot_btn.pressed_opacity = 0.75
        self.profile_forgot_btn.opacity = 1
        self.profile_forgot_btn.bind(on_release=self.open_password_recovery)
        self.profile_forgot_btn_row.add_widget(self.profile_forgot_btn)
        self.profile_forgot_btn_row.add_widget(Widget())
        self.password_panel.add_widget(self.profile_forgot_btn_row)

        self.password_panel_status = BodyLabel(
            center=True,
            color=COLORS["text_muted"],
            font_size=sp(10.5),
            size_hint_y=None,
            height=dp(18),
            text="",
        )
        self.password_panel.add_widget(self.password_panel_status)
        self.card.add_widget(self.password_panel_row)

        self.save_btn = AppButton(text="\u0421\u043e\u0437\u0434\u0430\u0442\u044c \u043f\u0440\u043e\u0444\u0438\u043b\u044c", font_size=sp(18))
        self.save_btn.height = dp(64)
        self.save_btn.bind(on_release=self.submit_profile)
        self.save_row = self._centered_row(self.save_btn, height=dp(64), width=self.button_width)
        self.card.add_widget(self.save_row)

        self.status_row = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(36))
        self.status_label = BodyLabel(
            center=True,
            color=COLORS["text_muted"],
            font_size=sp(11),
            text="После регистрации введи код из письма для подтверждения e-mail.",
        )
        self.status_label.size_hint_x = None
        self.status_label.width = self.field_width
        self.status_row.orientation = "horizontal"
        self.status_row.add_widget(Widget())
        self.status_row.add_widget(self.status_label)
        self.status_row.add_widget(Widget())
        self.card.add_widget(self.status_row)

        self.forgot_password_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(22))
        self.forgot_password_row.add_widget(Widget())
        self.forgot_password_btn = SubtleActionButton(text="Забыл пароль?")
        self.forgot_password_btn.size_hint = (None, None)
        self.forgot_password_btn.size = (dp(176), dp(22))
        self.forgot_password_btn.color = COLORS["text_soft"]
        self.forgot_password_btn.idle_opacity = 1
        self.forgot_password_btn.pressed_opacity = 0.75
        self.forgot_password_btn.opacity = 1
        self.forgot_password_btn.bind(on_release=self.open_password_recovery)
        self.forgot_password_row.add_widget(self.forgot_password_btn)
        self.forgot_password_row.add_widget(Widget())
        self.card.add_widget(self.forgot_password_row)

        self.logout_btn = AppButton(
            text="\u0412\u044b\u0445\u043e\u0434 \u0438\u0437 \u0430\u043a\u043a\u0430\u0443\u043d\u0442\u0430",
            compact=False,
            font_size=sp(17),
            button_color=COLORS["danger_button"],
            pressed_color=COLORS["danger_button_pressed"],
        )
        self.logout_btn.size_hint_y = None
        self.logout_btn.height = 0
        self.logout_btn.opacity = 0
        self.logout_btn.disabled = True
        self.logout_btn.bind(on_release=self._logout)
        self.logout_row = self._centered_row(self.logout_btn, height=0, width=self.button_width)
        self.card.add_widget(self.logout_row)

        content.add_widget(self.card)
        self.bottom_spacer = Widget(size_hint_y=None, height=dp(10))
        content.add_widget(self.bottom_spacer)

        self.scroll.add_widget(content)
        root.add_widget(self.scroll)
        self.coin_badge = CoinBadge(pos_hint={"right": 0.965, "top": 0.96})
        root.add_widget(self.coin_badge)
        self.add_widget(root)
        self.card.bind(size=self._update_form_widths, pos=self._update_form_widths)
        Clock.schedule_once(self._update_form_widths, 0)
        self._sync_avatar_actions()

    def _centered_row(self, widget, height, width=None):
        if width is not None:
            widget.size_hint_x = None
            widget.width = width

        widget.size_hint_y = None
        widget.height = height

        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=height)
        row.add_widget(Widget())
        row.add_widget(widget)
        row.add_widget(Widget())
        return row

    def on_pre_enter(self, *_):
        app = App.get_running_app()
        self.coin_badge.refresh_from_session()
        self.back_btn.text = "\u0412 \u043c\u0435\u043d\u044e" if app is not None and app.has_session_access() else "\u041d\u0430\u0437\u0430\u0434"
        self.scroll.scroll_y = 1

        latest_profile = app.current_profile() if app is not None and getattr(app, "authenticated", False) else None
        self._set_profile_mode(latest_profile is not None)
        self._set_coin_badge_visible(latest_profile is not None)

        if latest_profile is None:
            self.name_input.text = ""
            self.email_input.text = ""
            self.password_input.text = ""
            self.confirm_password_input.text = ""
            self.bio_input.text = ""
            self.selected_avatar_path = None
            self.avatar_preview.set_avatar(None)
            self.avatar_status_label.color = COLORS["text_muted"]
            self.avatar_status_label.text = "\u0424\u043e\u0442\u043e \u043d\u0435 \u0432\u044b\u0431\u0440\u0430\u043d\u043e."
            self.coins_stat.set_value(0)
            self.games_stat.set_value(0)
            self.points_stat.set_value(0)
            self.rooms_stat.set_value(0)
            self.status_label.color = COLORS["text_muted"]
            self.status_label.text = "Создай аккаунт. После этого придет 6-значный код на e-mail."
            return

        latest_profile = self._ensure_profile_avatar_ready(latest_profile)
        self.name_input.text = latest_profile.name
        self.email_input.text = latest_profile.email
        self.password_input.text = ""
        self.confirm_password_input.text = ""
        self.bio_input.text = latest_profile.bio or ""
        self.selected_avatar_path = latest_profile.avatar_path
        self.avatar_preview.set_avatar(latest_profile.avatar_source)
        self._apply_profile_summary(latest_profile)
        self.avatar_status_label.color = COLORS["text_muted"]
        self.avatar_status_label.text = Path(latest_profile.avatar_path).name if latest_profile.avatar_path else "\u0424\u043e\u0442\u043e \u043d\u0435 \u0432\u044b\u0431\u0440\u0430\u043d\u043e."
        self.status_label.color = COLORS["text_muted"]
        self.status_label.text = "\u041c\u043e\u0436\u043d\u043e \u0438\u0437\u043c\u0435\u043d\u0438\u0442\u044c \u043d\u0438\u043a, \u0444\u043e\u0442\u043e \u0438 \u043e\u043f\u0438\u0441\u0430\u043d\u0438\u0435 \u0442\u0435\u043a\u0443\u0449\u0435\u0433\u043e \u043f\u0440\u043e\u0444\u0438\u043b\u044f."
        self._sync_avatar_actions()

    def submit_profile(self, *_):
        app = App.get_running_app()
        try:
            if self.profile_mode:
                current_profile = app.current_profile() if app is not None and getattr(app, "authenticated", False) else None
                if current_profile is None:
                    raise ValueError("\u0421\u043d\u0430\u0447\u0430\u043b\u0430 \u0432\u043e\u0439\u0434\u0438 \u0432 \u0430\u043a\u043a\u0430\u0443\u043d\u0442.")

                profile = update_profile(
                    email=current_profile.email,
                    name=self.name_input.text,
                    avatar_path=self.selected_avatar_path,
                    bio=self.bio_input.text,
                )
            else:
                entered_password = self.password_input.text
                confirmed_password = self.confirm_password_input.text
                if entered_password != confirmed_password:
                    raise ValueError("\u041f\u0430\u0440\u043e\u043b\u0438 \u043d\u0435 \u0441\u043e\u0432\u043f\u0430\u0434\u0430\u044e\u0442. \u041f\u0440\u043e\u0432\u0435\u0440\u044c \u0438 \u043f\u043e\u0432\u0442\u043e\u0440\u0438 \u0432\u0432\u043e\u0434.")
                verification = begin_registration_verification(
                    name=self.name_input.text,
                    email=self.email_input.text,
                    password=entered_password,
                    bio=self.bio_input.text,
                    avatar_path=self.selected_avatar_path,
                )
        except ValueError as error:
            self.status_label.color = COLORS["error"]
            self.status_label.text = str(error)
            return

        self.password_input.text = ""
        if self.profile_mode:
            if app is not None:
                app.sign_in(profile)
            self.status_label.color = COLORS["success"]
            self.status_label.text = (
                f"\u041f\u0440\u043e\u0444\u0438\u043b\u044c {profile.name} \u043e\u0431\u043d\u043e\u0432\u043b\u0451\u043d. "
                "\u041f\u0435\u0440\u0435\u0445\u043e\u0434\u0438\u043c \u0432 \u043c\u0435\u043d\u044e."
            )
            self.manager.current = "start"
            return

        if app is not None:
            app.set_pending_registration_session(verification["session_id"])

        verification_screen = self.manager.get_screen("email_verification")
        verification_screen.start_verification(verification)
        self.status_label.color = COLORS["success"]
        self.status_label.text = "Код отправлен на e-mail. Подтверди регистрацию."
        self.manager.current = "email_verification"

    def open_avatar_picker(self, *_):
        chooser = FileChooserListView(
            path=str(Path.home()),
            filters=["*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp"],
            multiselect=False,
        )

        body = BoxLayout(orientation="vertical", spacing=dp(10), padding=[dp(14), dp(14), dp(14), dp(14)])
        body.add_widget(chooser)

        controls = BoxLayout(orientation="horizontal", spacing=dp(10), size_hint_y=None, height=dp(52))
        choose_btn = AppButton(text="\u0412\u044b\u0431\u0440\u0430\u0442\u044c", compact=True)
        close_btn = AppButton(text="\u041e\u0442\u043c\u0435\u043d\u0430", compact=True)
        choose_btn.bind(on_release=lambda *_: self.select_avatar_from_picker(chooser))
        close_btn.bind(on_release=lambda *_: self.dismiss_avatar_picker())
        controls.add_widget(choose_btn)
        controls.add_widget(close_btn)
        body.add_widget(controls)

        self.avatar_picker_popup = Popup(
            title="\u0412\u044b\u0431\u043e\u0440 \u0430\u0432\u0430\u0442\u0430\u0440\u0430",
            title_font="GameFont",
            title_size=sp(18),
            content=body,
            size_hint=(0.92, 0.82),
            auto_dismiss=True,
        )
        self.avatar_picker_popup.open()

    def dismiss_avatar_picker(self):
        if self.avatar_picker_popup is not None:
            self.avatar_picker_popup.dismiss()
            self.avatar_picker_popup = None

    def select_avatar_from_picker(self, chooser):
        selection = chooser.selection
        if not selection:
            self.avatar_status_label.color = COLORS["warning"]
            self.avatar_status_label.text = "\u0421\u043d\u0430\u0447\u0430\u043b\u0430 \u0432\u044b\u0431\u0435\u0440\u0438 \u0438\u0437\u043e\u0431\u0440\u0430\u0436\u0435\u043d\u0438\u0435 \u0432 \u0441\u043f\u0438\u0441\u043a\u0435 \u0444\u0430\u0439\u043b\u043e\u0432."
            return

        try:
            chosen_path = self._store_avatar_file(selection[0])
        except (OSError, ValueError) as error:
            self.avatar_status_label.color = COLORS["error"]
            self.avatar_status_label.text = str(error)
            return

        self.selected_avatar_path = chosen_path
        self.avatar_preview.set_avatar(chosen_path)
        self.avatar_status_label.color = COLORS["success"]
        self.avatar_status_label.text = Path(selection[0]).name
        self._sync_avatar_actions()
        self.dismiss_avatar_picker()

    def clear_avatar(self, *_):
        self.selected_avatar_path = None
        self.avatar_preview.set_avatar(None)
        self.avatar_status_label.color = COLORS["text_muted"]
        self.avatar_status_label.text = "\u0424\u043e\u0442\u043e \u0443\u0431\u0440\u0430\u043d\u043e."
        self._sync_avatar_actions()

    def _set_profile_mode(self, enabled):
        self.profile_mode = enabled

        if enabled:
            self.profile_header.height = dp(34)
            self.profile_header.opacity = 1
            self.profile_title.font_size = sp(14)
            self.profile_summary.font_size = sp(9)
            self.title_label.text = "\u041f\u0440\u043e\u0444\u0438\u043b\u044c"
            self.title_label.font_size = sp(16)
            self.title_label.height = 0
            self.title_label.opacity = 0
            self.subtitle_label.text = ""
            self.subtitle_label.font_size = sp(9.5)
            self.avatar_mode_note.text = "\u0424\u043e\u0442\u043e \u043f\u0440\u043e\u0444\u0438\u043b\u044f"
            self.scroll.do_scroll_y = False
            self.content.spacing = dp(4)
            self.content.padding = [dp(8), dp(8), dp(8), dp(6)]
            self.card.spacing = dp(4)
            self.card.padding = [dp(16), dp(12), dp(16), dp(12)]
            self.brand_title.height = dp(44)
            self.brand_title.set_style(font_size=sp(26), shadow_step=dp(2))
            self.profile_header.height = dp(34)
            self.top_spacer.height = dp(4)
            self.bottom_spacer.height = dp(4)
            self.subtitle_row.height = 0
            self.subtitle_row.opacity = 0
            self.name_caption_row.height = dp(14)
            self.name_caption_row.opacity = 1
            self.name_caption.font_size = sp(10)
            self.email_caption.text = "E-mail"
            self.email_caption_row.height = dp(14)
            self.email_caption_row.opacity = 1
            self.email_caption.font_size = sp(10)
            self.name_row.height = dp(40)
            self.email_row.height = dp(40)
            self.name_input.height = dp(40)
            self.email_input.height = dp(40)
            self.name_input.font_size = sp(14)
            self.email_input.font_size = sp(14)
            self.name_input.padding = self.profile_input_padding[:]
            self.email_input.padding = self.profile_input_padding[:]
            self.name_input.readonly = False
            self.email_input.readonly = True
            self.name_input.disabled = False
            self.email_input.disabled = False
            self.password_row.height = 0
            self.password_row.opacity = 0
            self.password_input.disabled = True
            self.confirm_password_input.text = ""
            self.confirm_password_row.height = 0
            self.confirm_password_row.opacity = 0
            self.confirm_password_input.disabled = True
            self.stats_wrap.height = dp(110)
            self.stats_wrap.opacity = 1
            self.avatar_mode_note_row.height = 0
            self.avatar_mode_note_row.opacity = 0
            self.avatar_section.spacing = dp(8)
            self.avatar_section.padding = [dp(12), dp(12), dp(12), dp(12)]
            self.avatar_section_row.height = dp(166)
            self.avatar_preview.size = (dp(60), dp(60))
            self.preview_row.height = dp(64)
            self.avatar_button_gap.height = dp(6)
            self.add_photo_row.height = dp(34)
            self.pick_avatar_btn.size = (dp(170), dp(32))
            self.avatar_section.height = dp(166)
            self.avatar_section.opacity = 1
            self.avatar_status_row.height = dp(18)
            self.avatar_status_row.opacity = 1
            self.bio_row.height = dp(46)
            self.bio_input.height = dp(46)
            self.bio_input.font_size = sp(14)
            self.bio_input.hint_text = "\u0420\u0430\u0441\u0441\u043a\u0430\u0436\u0438 \u043f\u0430\u0440\u0443 \u0441\u043b\u043e\u0432 \u043e \u0441\u0435\u0431\u0435"
            self.password_panel.spacing = dp(4)
            self.password_panel.padding = [dp(10), dp(8), dp(10), dp(8)]
            self.password_panel_title.height = 0
            self.password_panel_title.opacity = 0
            self.change_password_btn_row.height = dp(34)
            self.change_password_btn.size = (dp(170), dp(32))
            self.profile_forgot_btn_row.height = dp(24)
            self.password_panel_status.height = 0
            self.password_panel_status.opacity = 0
            self.password_panel_row.height = dp(92)
            self.password_panel.height = dp(92)
            self.password_panel.opacity = 1
            self.current_password_input.height = 0
            self.new_password_input.height = 0
            self.password_panel_status.text = ""
            self.pick_avatar_btn.disabled = False
            self.save_row.height = dp(44)
            self.save_btn.height = dp(44)
            self.status_row.height = 0
            self.status_row.opacity = 0
            self.forgot_password_row.height = 0
            self.forgot_password_row.opacity = 0
            self.card.height = dp(680)
            self.logout_btn.disabled = False
            self.logout_btn.opacity = 1
            self.logout_row.height = dp(44)
            self.logout_btn.height = dp(44)
            self._update_form_widths()
            self._sync_avatar_actions()
            self.save_btn.text = "\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u0438\u0437\u043c\u0435\u043d\u0435\u043d\u0438\u044f"
            return

        self.profile_header.height = 0
        self.profile_header.opacity = 0
        self.profile_summary.text = ""
        self.title_label.text = "\u0420\u0435\u0433\u0438\u0441\u0442\u0440\u0430\u0446\u0438\u044f"
        self.title_label.font_size = sp(18)
        self.title_label.height = dp(28)
        self.title_label.opacity = 1
        self.subtitle_label.text = "\u0421\u043e\u0437\u0434\u0430\u0439 \u043f\u0440\u043e\u0444\u0438\u043b\u044c, \u0447\u0442\u043e\u0431\u044b \u0432\u043e\u0439\u0442\u0438 \u0432 \u0438\u0433\u0440\u0443."
        self.subtitle_label.font_size = sp(12)
        self.avatar_mode_note.text = "\u0424\u043e\u0442\u043e \u043c\u043e\u0436\u043d\u043e \u0434\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0441\u0440\u0430\u0437\u0443 \u0438\u043b\u0438 \u043f\u043e\u0437\u0436\u0435 \u0432 \u043f\u0440\u043e\u0444\u0438\u043b\u0435."
        self.scroll.do_scroll_y = True
        self.content.spacing = self.default_content_spacing
        self.content.padding = self.default_content_padding
        self.card.spacing = self.default_card_spacing
        self.card.padding = self.default_card_padding
        self.brand_title.height = dp(136)
        self.brand_title.set_style(font_size=sp(44), shadow_step=dp(3))
        self.profile_header.height = 0
        self.top_spacer.height = dp(10)
        self.bottom_spacer.height = dp(10)
        self.subtitle_row.height = dp(32)
        self.subtitle_row.opacity = 1
        self.name_caption_row.height = 0
        self.name_caption_row.opacity = 0
        self.name_caption.font_size = sp(11)
        self.email_caption_row.height = 0
        self.email_caption_row.opacity = 0
        self.email_caption.font_size = sp(11)
        self.name_row.height = dp(48)
        self.email_row.height = dp(48)
        self.name_input.height = dp(48)
        self.email_input.height = dp(48)
        self.name_input.font_size = sp(16)
        self.email_input.font_size = sp(16)
        self.name_input.padding = self.default_input_padding[:]
        self.email_input.padding = self.default_input_padding[:]
        self.password_input.padding = self.default_input_padding[:]
        self.confirm_password_input.padding = self.default_input_padding[:]
        self.name_input.readonly = False
        self.email_input.readonly = False
        self.name_input.disabled = False
        self.email_input.disabled = False
        self.password_row.height = dp(48)
        self.password_row.opacity = 1
        self.password_input.disabled = False
        self.confirm_password_input.text = ""
        self.confirm_password_row.height = dp(48)
        self.confirm_password_row.opacity = 1
        self.confirm_password_input.disabled = False
        self.stats_wrap.height = 0
        self.stats_wrap.opacity = 0
        self.avatar_mode_note_row.height = dp(20)
        self.avatar_mode_note_row.opacity = 1
        self.avatar_section.spacing = dp(8)
        self.avatar_section.padding = [dp(14), dp(12), dp(14), dp(12)]
        self.avatar_preview.size = (dp(88), dp(88))
        self.preview_row.height = dp(92)
        self.avatar_button_gap.height = dp(12)
        self.add_photo_row.height = dp(42)
        self.pick_avatar_btn.size = (dp(210), dp(40))
        self.avatar_section_row.height = dp(206)
        self.avatar_section.height = dp(204)
        self.avatar_section.opacity = 1
        self.avatar_status_row.height = dp(18)
        self.avatar_status_row.opacity = 1
        self.bio_row.height = dp(72)
        self.bio_input.height = dp(72)
        self.bio_input.font_size = sp(16)
        self.bio_input.hint_text = "\u041e\u043f\u0438\u0441\u0430\u043d\u0438\u0435 \u043f\u0440\u043e\u0444\u0438\u043b\u044f (\u043d\u0435\u043e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u044c\u043d\u043e)"
        self.password_panel_row.height = 0
        self.password_panel.height = 0
        self.password_panel.opacity = 0
        self.password_panel.spacing = dp(6)
        self.password_panel.padding = [dp(12), dp(10), dp(12), dp(10)]
        self.password_panel_title.height = dp(20)
        self.password_panel_title.opacity = 1
        self.change_password_btn_row.height = dp(36)
        self.change_password_btn.size = (dp(186), dp(34))
        self.profile_forgot_btn_row.height = dp(24)
        self.password_panel_status.height = dp(18)
        self.password_panel_status.opacity = 1
        self.current_password_input.text = ""
        self.new_password_input.text = ""
        self.current_password_input.height = 0
        self.new_password_input.height = 0
        self.password_panel_status.text = ""
        self.pick_avatar_btn.disabled = False
        self._sync_avatar_actions()
        self.save_row.height = dp(64)
        self.save_btn.height = dp(64)
        self.status_row.height = dp(36)
        self.status_row.opacity = 1
        self.forgot_password_row.height = dp(22)
        self.forgot_password_row.opacity = 0.85
        self.card.height = dp(760)
        self.logout_btn.disabled = True
        self.logout_btn.opacity = 0
        self.logout_row.height = 0
        self.logout_btn.height = 0
        self.save_btn.text = "\u0421\u043e\u0437\u0434\u0430\u0442\u044c \u043f\u0440\u043e\u0444\u0438\u043b\u044c"
        self._update_form_widths()

    def _set_coin_badge_visible(self, visible):
        self.coin_badge.opacity = 1 if visible else 0
        self.coin_badge.disabled = not visible

    def _update_form_widths(self, *_):
        if not getattr(self, "card", None):
            return

        horizontal_padding = 0
        if isinstance(self.card.padding, (list, tuple)) and len(self.card.padding) >= 2:
            horizontal_padding = self.card.padding[0] + self.card.padding[2]

        inner_width = max(dp(220), self.card.width - horizontal_padding)
        field_width = min(self.field_width, inner_width - dp(6))
        button_width = min(self.button_width, inner_width - dp(6))
        avatar_width = min(self.avatar_panel_width, inner_width - dp(6))

        for widget in (self.name_input, self.email_input, self.password_input, self.confirm_password_input, self.bio_input):
            widget.size_hint_x = None
            widget.width = field_width

        self.password_panel.size_hint_x = None
        self.password_panel.width = field_width
        self.name_caption.width = field_width
        self.email_caption.width = field_width
        self.status_label.width = field_width

        self.save_btn.size_hint_x = None
        self.save_btn.width = button_width
        self.logout_btn.size_hint_x = None
        self.logout_btn.width = button_width

        self.avatar_section.size_hint_x = None
        self.avatar_section.width = avatar_width
        self.pick_avatar_btn.size_hint_x = None
        self.pick_avatar_btn.width = max(dp(132), min(dp(210), avatar_width - dp(28)))

    def _apply_profile_summary(self, profile):
        joined_label = self._format_profile_date(profile.created_at)
        summary = f"\u041a\u043e\u0434 \u0438\u0433\u0440\u043e\u043a\u0430 #{profile.id} | \u0432 \u0438\u0433\u0440\u0435 \u0441 {joined_label}"
        self.profile_summary.text = summary
        self.subtitle_label.text = summary
        self.coins_stat.set_value(profile.games_played)
        self.games_stat.set_value(profile.total_points)
        self.points_stat.set_value(profile.guessed_words)
        self.rooms_stat.set_value(profile.explained_words)

    def _format_profile_date(self, created_at):
        raw_value = (created_at or "").strip()
        if not raw_value:
            return "--.--.----"

        try:
            parsed = datetime.strptime(raw_value, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return raw_value

        return parsed.strftime("%d.%m.%Y")

    def _sync_avatar_actions(self):
        has_avatar = bool(self.selected_avatar_path)
        self.clear_avatar_btn.disabled = not has_avatar
        self.clear_avatar_btn.opacity = 0.85 if has_avatar else 0
        self.clear_avatar_btn.height = dp(20) if has_avatar else 0
        self.clear_row.height = dp(20) if has_avatar else 0

    def _avatar_storage_dir(self):
        app = App.get_running_app()
        if app is not None and getattr(app, "user_data_dir", None):
            return Path(app.user_data_dir) / "avatars"
        return Path(__file__).resolve().parents[1] / "data" / "avatars"

    def _ensure_profile_avatar_ready(self, profile):
        if profile is None or not profile.avatar_path:
            return profile

        avatar_path = Path(profile.avatar_path).expanduser()
        if not avatar_path.exists():
            return profile

        storage_dir = self._avatar_storage_dir().resolve()
        resolved_avatar = avatar_path.resolve()
        if resolved_avatar.suffix.lower() == ".png" and resolved_avatar.parent == storage_dir:
            return profile

        try:
            normalized_path = self._store_avatar_file(resolved_avatar)
        except ValueError:
            return profile

        return update_profile(email=profile.email, avatar_path=normalized_path, bio=profile.bio)

    def _store_avatar_file(self, source_path):
        from PIL import Image as PILImage, ImageOps, UnidentifiedImageError

        source = Path(source_path).expanduser()
        if not source.exists():
            raise ValueError("\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043d\u0430\u0439\u0442\u0438 \u0432\u044b\u0431\u0440\u0430\u043d\u043d\u043e\u0435 \u0444\u043e\u0442\u043e.")

        extension = source.suffix.lower()
        if extension not in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
            raise ValueError("\u042d\u0442\u043e\u0442 \u0444\u043e\u0440\u043c\u0430\u0442 \u0444\u043e\u0442\u043e \u043f\u043e\u043a\u0430 \u043d\u0435 \u043f\u043e\u0434\u0434\u0435\u0440\u0436\u0438\u0432\u0430\u0435\u0442\u0441\u044f.")

        target_dir = self._avatar_storage_dir()
        target_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        target_path = target_dir / f"avatar_{timestamp}.png"

        try:
            with PILImage.open(source) as image:
                prepared = ImageOps.exif_transpose(image).convert("RGBA")
                side = min(prepared.size)
                left = max(0, int((prepared.width - side) / 2))
                top = max(0, int((prepared.height - side) / 2))
                avatar_image = prepared.crop((left, top, left + side, top + side))
                resampling = getattr(getattr(PILImage, "Resampling", PILImage), "LANCZOS", PILImage.LANCZOS)
                avatar_image.thumbnail((512, 512), resampling)
                avatar_image.save(target_path, format="PNG", optimize=True)
        except (OSError, UnidentifiedImageError) as error:
            raise ValueError("\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043e\u0442\u043a\u0440\u044b\u0442\u044c \u044d\u0442\u043e \u0444\u043e\u0442\u043e. \u0412\u044b\u0431\u0435\u0440\u0438 \u0434\u0440\u0443\u0433\u043e\u0439 \u0444\u0430\u0439\u043b.") from error

        return str(target_path.resolve())

    def open_password_recovery(self, *_):
        recovery_screen = self.manager.get_screen("password_recovery")
        default_email = self.email_input.text
        recovery_screen.start_flow(default_email=default_email, return_screen=self.name)
        self.manager.current = "password_recovery"

    def open_change_password_dialog(self, *_):
        if not self.profile_mode:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Смена пароля доступна после входа в аккаунт."
            return

        app = App.get_running_app()
        profile = app.current_profile() if app is not None and getattr(app, "authenticated", False) else None
        if profile is None:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Сначала войди в аккаунт."
            return

        current_password_input = AppTextInput(hint_text="Текущий пароль", password=True, height=dp(48))
        new_password_input = AppTextInput(hint_text="Новый пароль", password=True, height=dp(48))
        dialog_status = BodyLabel(center=True, color=COLORS["text_muted"], font_size=sp(11), text="")

        body = BoxLayout(orientation="vertical", spacing=dp(8), padding=[dp(12), dp(12), dp(12), dp(12)])
        body.add_widget(current_password_input)
        body.add_widget(new_password_input)
        body.add_widget(dialog_status)

        forgot_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(20))
        forgot_row.add_widget(Widget())
        forgot_btn = SubtleActionButton(text="Забыл пароль?")
        forgot_row.add_widget(forgot_btn)
        forgot_row.add_widget(Widget())
        body.add_widget(forgot_row)

        actions = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(42))
        save_btn = AppButton(text="Сменить", compact=True)
        cancel_btn = AppButton(text="Отмена", compact=True)
        actions.add_widget(save_btn)
        actions.add_widget(cancel_btn)
        body.add_widget(actions)

        popup = Popup(
            title="Изменить пароль",
            title_font="GameFont",
            title_size=sp(18),
            content=body,
            size_hint=(0.9, 0.54),
            auto_dismiss=True,
        )
        self.change_password_popup = popup
        popup.bind(on_dismiss=lambda *_: setattr(self, "change_password_popup", None))

        def apply_change(*_):
            try:
                change_profile_password(
                    email=profile.email,
                    current_password=current_password_input.text,
                    new_password=new_password_input.text,
                )
            except ValueError as error:
                dialog_status.color = COLORS["error"]
                dialog_status.text = str(error)
                return

            self.password_panel_status.color = COLORS["success"]
            self.password_panel_status.text = "Пароль успешно изменён."
            self.status_label.color = COLORS["success"]
            self.status_label.text = "Пароль изменён."
            popup.dismiss()
            self.change_password_popup = None

        def open_recovery(*_):
            popup.dismiss()
            self.change_password_popup = None
            self.open_password_recovery()

        save_btn.bind(on_release=apply_change)
        cancel_btn.bind(on_release=lambda *_: popup.dismiss())
        forgot_btn.bind(on_release=open_recovery)
        popup.open()

    def _go_back(self, *_):
        app = App.get_running_app()
        if app is not None and app.has_session_access():
            self.manager.current = "start"
            return
        self.manager.current = "entry"

    def _logout(self, *_):
        app = App.get_running_app()
        if app is not None:
            app.sign_out()
        self.manager.current = "entry"
