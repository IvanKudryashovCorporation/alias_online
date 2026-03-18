from kivy.app import App
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from ui import AppButton, BodyLabel, BrandTitle, CoinBadge, COLORS, RoundedPanel, ScreenBackground, register_game_font


class EntryScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        register_game_font()

        root = ScreenBackground()

        content = BoxLayout(
            orientation="vertical",
            spacing=dp(12),
            padding=[dp(20), dp(22), dp(20), dp(22)],
        )

        content.add_widget(Widget(size_hint_y=None, height=dp(12)))
        content.add_widget(BrandTitle(height=dp(280), font_size=sp(58)))
        content.add_widget(
            BodyLabel(
                center=True,
                color=COLORS["text_soft"],
                font_size=sp(14),
                size_hint_y=None,
                height=dp(26),
                text="Выбери, как хочешь начать игру.",
            )
        )
        content.add_widget(Widget())

        card = RoundedPanel(
            orientation="vertical",
            padding=[dp(16), dp(16), dp(16), dp(16)],
            spacing=dp(14),
            size_hint_y=None,
            height=dp(292),
        )

        login_btn = AppButton(text="Войти", font_size=sp(22))
        register_btn = AppButton(text="Зарегистрироваться", font_size=sp(22))
        guest_btn = AppButton(text="Играть как гость", font_size=sp(20))

        for button in (login_btn, register_btn, guest_btn):
            button.height = dp(72)
            card.add_widget(button)

        login_btn.bind(on_release=lambda *_: setattr(self.manager, "current", "login"))
        register_btn.bind(on_release=self._go_to_registration)
        guest_btn.bind(on_release=self._play_as_guest)

        content.add_widget(card)
        content.add_widget(Widget())

        root.add_widget(content)
        self.coin_badge = CoinBadge(pos_hint={"right": 0.965, "top": 0.96})
        root.add_widget(self.coin_badge)
        self.add_widget(root)

    def on_pre_enter(self, *_):
        self.coin_badge.refresh_from_session()

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
