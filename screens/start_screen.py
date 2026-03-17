from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle, StencilPop, StencilPush, StencilUnUse, StencilUse
from kivy.app import App
from kivy.metrics import dp, sp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from ui import AvatarButton, AppButton, BodyLabel, BrandTitle, COLORS, PixelLabel, RoundedPanel, ScreenBackground, register_game_font

APP_VERSION = "0.1.0"


class ProfileNameButton(ButtonBehavior, BodyLabel):
    def __init__(self, **kwargs):
        super().__init__(center=True, **kwargs)
        self.opacity = 1

    def on_press(self):
        self.opacity = 0.72

    def on_release(self):
        self.opacity = 1


class SupportIconButton(ButtonBehavior, Widget):
    def __init__(self, **kwargs):
        register_game_font()
        super().__init__(size_hint=(None, None), size=(dp(52), dp(52)), **kwargs)

        with self.canvas.before:
            self._shadow_color = Color(0, 0, 0, 0.22)
            self._shadow = RoundedRectangle(radius=[dp(18)] * 4)
            self._bg_color = Color(*COLORS["surface"])
            self._bg = RoundedRectangle(radius=[dp(18)] * 4)
            self._border_color = Color(*COLORS["outline"])
            self._border = Line(width=1.1, rounded_rectangle=(self.x, self.y, self.width, self.height, dp(18)))

        self._icon = Label(
            text="?",
            font_name="BrandFont",
            font_size=sp(28),
            color=COLORS["text"],
            halign="center",
            valign="middle",
        )
        self.add_widget(self._icon)
        self.bind(pos=self._sync_canvas, size=self._sync_canvas)

    def _sync_canvas(self, *_):
        self._shadow.pos = (self.x, self.y - dp(2))
        self._shadow.size = self.size
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._border.rounded_rectangle = (self.x, self.y, self.width, self.height, dp(18))
        self._icon.pos = self.pos
        self._icon.size = self.size
        self._icon.text_size = self.size

    def on_press(self):
        self._bg_color.rgba = COLORS["button_pressed"]

    def on_release(self):
        self._bg_color.rgba = COLORS["surface"]


class LanguageFlagBadge(Widget):
    def __init__(self, **kwargs):
        super().__init__(size_hint=(None, None), size=(dp(42), dp(42)), **kwargs)

        with self.canvas.before:
            self._shadow_color = Color(0, 0, 0, 0.20)
            self._shadow = Ellipse(pos=self.pos, size=self.size)

            StencilPush()
            self._mask = Ellipse(pos=self.pos, size=self.size)
            StencilUse()

            self._white_color = Color(1, 1, 1, 1)
            self._white_band = Rectangle()
            self._blue_color = Color(0.12, 0.35, 0.82, 1)
            self._blue_band = Rectangle()
            self._red_color = Color(0.84, 0.16, 0.2, 1)
            self._red_band = Rectangle()

            StencilUnUse()
            self._outline_color = Color(1, 1, 1, 0.18)
            self._outline = Line(width=1.2, ellipse=(self.x, self.y, self.width, self.height))
            StencilPop()

        self.bind(pos=self._sync_canvas, size=self._sync_canvas)

    def _sync_canvas(self, *_):
        self._shadow.pos = (self.x, self.y - dp(2))
        self._shadow.size = self.size
        self._mask.pos = self.pos
        self._mask.size = self.size

        band_height = self.height / 3
        self._red_band.pos = self.pos
        self._red_band.size = (self.width, band_height)
        self._blue_band.pos = (self.x, self.y + band_height)
        self._blue_band.size = (self.width, band_height)
        self._white_band.pos = (self.x, self.y + band_height * 2)
        self._white_band.size = (self.width, self.height - band_height * 2)
        self._outline.ellipse = (self.x, self.y, self.width, self.height)


class StartScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        register_game_font()
        self.guest_access_popup = None
        self.support_popup = None

        root = ScreenBackground()

        self.support_button = SupportIconButton(pos_hint={"x": 0.04, "top": 0.957})
        self.support_button.bind(on_release=self._open_support_popup)

        self.profile_corner = BoxLayout(
            orientation="vertical",
            spacing=dp(6),
            size_hint=(None, None),
            size=(dp(114), dp(94)),
            pos_hint={"right": 0.965, "top": 0.96},
        )

        avatar_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(64))
        avatar_row.add_widget(Widget())
        self.avatar_button = AvatarButton()
        self.avatar_button.bind(on_release=self._on_profile_pressed)
        avatar_row.add_widget(self.avatar_button)
        avatar_row.add_widget(Widget())
        self.profile_corner.add_widget(avatar_row)

        self.profile_name_label = ProfileNameButton(
            size_hint_y=None,
            height=dp(20),
            font_size=sp(11),
            color=COLORS["text"],
            shorten=True,
            shorten_from="center",
            text="",
        )
        self.profile_name_label.bind(on_release=self._on_profile_pressed)
        self.profile_corner.add_widget(self.profile_name_label)

        content = BoxLayout(
            orientation="vertical",
            spacing=dp(6),
            padding=[dp(20), dp(24), dp(20), dp(18)],
        )

        content.add_widget(Widget(size_hint_y=None, height=dp(14)))
        content.add_widget(BrandTitle(height=dp(286), font_size=sp(62)))

        language_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(58))
        language_row.add_widget(Widget())
        self.language_badge = LanguageFlagBadge()
        language_row.add_widget(self.language_badge)
        language_row.add_widget(Widget())
        content.add_widget(language_row)
        content.add_widget(Widget(size_hint_y=None, height=dp(10)))

        menu_holder = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(352),
            spacing=dp(14),
        )

        create_btn = AppButton(text="Создать комнату", font_size=sp(22))
        join_btn = AppButton(text="Войти в комнату", font_size=sp(22))
        friends_btn = AppButton(text="Друзья", font_size=sp(22))
        rules_btn = AppButton(text="Правила", font_size=sp(22))

        for button in (create_btn, join_btn, friends_btn, rules_btn):
            button.height = dp(74)
            menu_holder.add_widget(button)

        create_btn.bind(on_release=lambda *_: setattr(self.manager, "current", "create_room"))
        join_btn.bind(on_release=lambda *_: setattr(self.manager, "current", "join_room"))
        friends_btn.bind(on_release=lambda *_: setattr(self.manager, "current", "friends"))
        rules_btn.bind(on_release=lambda *_: setattr(self.manager, "current", "rules"))

        content.add_widget(menu_holder)
        content.add_widget(Widget())

        self.version_label = BodyLabel(
            center=True,
            size_hint=(None, None),
            size=(dp(160), dp(18)),
            pos_hint={"center_x": 0.5, "y": 0.016},
            font_size=sp(11),
            color=COLORS["text_muted"],
            text=f"Версия {APP_VERSION}",
        )

        root.add_widget(content)
        root.add_widget(self.support_button)
        root.add_widget(self.profile_corner)
        root.add_widget(self.version_label)
        self.add_widget(root)

    def on_pre_enter(self, *_):
        self.refresh_profile()

    def on_leave(self, *_):
        self._dismiss_guest_access_popup()
        self._dismiss_support_popup()

    def refresh_profile(self):
        app = App.get_running_app()
        player_name = app.resolve_player_name() if app is not None else ""

        if app is not None and getattr(app, "guest_mode", False):
            self.avatar_button.set_profile(None)
            self.profile_name_label.text = player_name or "Гость"
            return

        profile = app.current_profile() if app is not None else None
        self.avatar_button.set_profile(profile)
        self.profile_name_label.text = player_name or ""

    def _on_profile_pressed(self, *_):
        app = App.get_running_app()
        if app is not None and getattr(app, "guest_mode", False):
            self._open_guest_access_popup()
            return

        self.manager.current = "registration"

    def _open_guest_access_popup(self):
        self._dismiss_guest_access_popup()

        body = BoxLayout(
            orientation="vertical",
            spacing=dp(12),
            padding=[dp(16), dp(16), dp(16), dp(16)],
        )

        panel = RoundedPanel(
            orientation="vertical",
            spacing=dp(12),
            padding=[dp(16), dp(16), dp(16), dp(16)],
            size_hint_y=None,
            height=dp(270),
        )
        panel.add_widget(PixelLabel(text="Гостевой режим", font_size=sp(18), center=True, size_hint_y=None))
        panel.add_widget(
            BodyLabel(
                center=True,
                color=COLORS["text_muted"],
                font_size=sp(12),
                text="Чтобы открыть профиль и сохранить данные, войди в аккаунт или зарегистрируйся.",
            )
        )

        login_btn = AppButton(text="Войти", font_size=sp(18))
        login_btn.height = dp(62)
        login_btn.bind(on_release=self._go_to_login)
        panel.add_widget(login_btn)

        register_btn = AppButton(text="Зарегистрироваться", font_size=sp(18))
        register_btn.height = dp(62)
        register_btn.bind(on_release=self._go_to_registration)
        panel.add_widget(register_btn)

        close_btn = AppButton(text="Закрыть", compact=True, font_size=sp(14))
        close_btn.height = dp(44)
        close_btn.bind(on_release=lambda *_: self._dismiss_guest_access_popup())
        panel.add_widget(close_btn)

        body.add_widget(panel)

        self.guest_access_popup = Popup(
            title="",
            separator_height=0,
            auto_dismiss=True,
            background="atlas://data/images/defaulttheme/modalview-background",
            content=body,
            size_hint=(0.82, None),
            height=dp(320),
        )
        self.guest_access_popup.bind(on_dismiss=lambda *_: setattr(self, "guest_access_popup", None))
        self.guest_access_popup.open()

    def _dismiss_guest_access_popup(self):
        if self.guest_access_popup is not None:
            popup = self.guest_access_popup
            self.guest_access_popup = None
            popup.dismiss()

    def _open_support_popup(self, *_):
        self._dismiss_support_popup()

        body = BoxLayout(
            orientation="vertical",
            spacing=dp(12),
            padding=[dp(16), dp(16), dp(16), dp(16)],
        )

        panel = RoundedPanel(
            orientation="vertical",
            spacing=dp(12),
            padding=[dp(16), dp(16), dp(16), dp(16)],
            size_hint_y=None,
            height=dp(210),
        )
        panel.add_widget(PixelLabel(text="Поддержка", font_size=sp(18), center=True, size_hint_y=None))
        panel.add_widget(
            BodyLabel(
                center=True,
                color=COLORS["text_muted"],
                font_size=sp(12),
                text="Раздел помощи скоро появится. Здесь будут ответы, связь с поддержкой и FAQ.",
            )
        )

        close_btn = AppButton(text="Закрыть", compact=True, font_size=sp(14))
        close_btn.height = dp(44)
        close_btn.bind(on_release=lambda *_: self._dismiss_support_popup())
        panel.add_widget(close_btn)

        body.add_widget(panel)

        self.support_popup = Popup(
            title="",
            separator_height=0,
            auto_dismiss=True,
            background="atlas://data/images/defaulttheme/modalview-background",
            content=body,
            size_hint=(0.78, None),
            height=dp(260),
        )
        self.support_popup.bind(on_dismiss=lambda *_: setattr(self, "support_popup", None))
        self.support_popup.open()

    def _dismiss_support_popup(self):
        if self.support_popup is not None:
            popup = self.support_popup
            self.support_popup = None
            popup.dismiss()

    def _go_to_login(self, *_):
        app = App.get_running_app()
        if app is not None:
            app.sign_out()
        self._dismiss_guest_access_popup()
        self.manager.current = "login"

    def _go_to_registration(self, *_):
        app = App.get_running_app()
        if app is not None:
            app.start_registration_flow()
        self._dismiss_guest_access_popup()
        self.manager.current = "registration"
