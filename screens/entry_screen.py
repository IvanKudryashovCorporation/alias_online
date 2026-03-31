from kivy.app import App
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from ui import (
    AppButton,
    BodyLabel,
    BrandTitle,
    COLORS,
    RoundedPanel,
    ScreenBackground,
    register_game_font,
)


class EntryScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        register_game_font()

        root = ScreenBackground()

        content = BoxLayout(
            orientation="vertical",
            spacing=dp(12),
            padding=[dp(18), dp(16), dp(18), dp(18)],
        )
        content.add_widget(Widget(size_hint_y=None, height=dp(4)))
        content.add_widget(BrandTitle(height=dp(338), font_size=sp(84), shadow_step=dp(5)))

        mode_hint_card = RoundedPanel(
            orientation="vertical",
            size_hint_y=None,
            height=dp(58),
            padding=[dp(14), dp(10), dp(14), dp(10)],
            bg_color=(0.11, 0.19, 0.30, 0.80),
        )
        mode_hint_card._border_color.rgba = (0.99, 0.95, 0.36, 0.32)
        mode_hint_card._border_line.width = 1.4
        mode_hint_card.add_widget(
            BodyLabel(
                center=True,
                color=COLORS["accent"],
                font_size=sp(20),
                size_hint_y=None,
                text="Выбери, как хочешь начать игру",
            )
        )
        content.add_widget(mode_hint_card)

        menu_card = RoundedPanel(
            orientation="vertical",
            padding=[dp(18), dp(18), dp(18), dp(18)],
            spacing=dp(12),
            size_hint_y=None,
            height=dp(316),
            bg_color=COLORS["surface_card"],
        )
        menu_card._border_color.rgba = (1, 1, 1, 0.16)
        menu_card._border_line.width = 1.3

        login_btn = AppButton(text="Войти", font_size=sp(22))
        register_btn = AppButton(text="Зарегистрироваться", font_size=sp(22))
        login_btn.height = dp(80)
        register_btn.height = dp(80)
        menu_card.add_widget(login_btn)
        menu_card.add_widget(register_btn)

        guest_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(42))
        guest_row.add_widget(Widget())
        guest_btn = AppButton(
            text="Играть как гость",
            compact=True,
            font_size=sp(13),
            size_hint=(None, None),
            size=(dp(188), dp(34)),
            button_color=(0.10, 0.16, 0.26, 0.62),
            pressed_color=(0.09, 0.14, 0.23, 0.76),
        )
        guest_row.add_widget(guest_btn)
        guest_row.add_widget(Widget())
        menu_card.add_widget(guest_row)

        hint = BodyLabel(
            center=True,
            color=COLORS["text_muted"],
            font_size=sp(10.5),
            size_hint_y=None,
            text="Гость может играть сразу, а профиль откроет сохранение статистики.",
        )
        menu_card.add_widget(hint)

        login_btn.bind(on_release=lambda *_: setattr(self.manager, "current", "login"))
        register_btn.bind(on_release=self._go_to_registration)
        guest_btn.bind(on_release=self._play_as_guest)

        content.add_widget(menu_card)
        content.add_widget(Widget())

        root.add_widget(content)
        self.add_widget(root)

    def _go_to_registration(self, *_):
        app = App.get_running_app()
        if app is not None:
            app.start_registration_flow()
        self.manager.current = "registration"

    def _play_as_guest(self, *_):
        app = App.get_running_app()
        if app is not None:
            app.enter_guest_mode()
        self.manager.current = "start"
