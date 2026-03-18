from kivy.app import App
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from services import has_profiles, login_profile
from ui import AppButton, AppTextInput, BodyLabel, BrandTitle, CoinBadge, COLORS, PixelLabel, RoundedPanel, ScreenBackground, register_game_font


class LoginScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        register_game_font()

        root = ScreenBackground()

        content = BoxLayout(
            orientation="vertical",
            spacing=dp(10),
            padding=[dp(18), dp(18), dp(18), dp(18)],
        )

        top_bar = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48))
        back_btn = AppButton(text="Назад", compact=True, size_hint=(None, None), size=(dp(128), dp(46)))
        back_btn.bind(on_release=lambda *_: setattr(self.manager, "current", "entry"))
        top_bar.add_widget(back_btn)
        top_bar.add_widget(Widget())
        content.add_widget(top_bar)

        content.add_widget(BrandTitle(text="ALIAS ONLINE", height=dp(136), font_size=sp(44), shadow_step=dp(3)))

        card = RoundedPanel(
            orientation="vertical",
            padding=[dp(16), dp(16), dp(16), dp(16)],
            spacing=dp(10),
            size_hint_y=None,
            height=dp(330),
        )
        card.add_widget(PixelLabel(text="Вход", font_size=sp(22), center=True, size_hint_y=None, height=dp(30)))
        card.add_widget(
            BodyLabel(
                center=True,
                color=COLORS["text_muted"],
                font_size=sp(13),
                size_hint_y=None,
                height=dp(24),
                text="Введи почту и пароль от сохранённого профиля.",
            )
        )

        self.email_input = AppTextInput(hint_text="E-mail", height=dp(52))
        self.password_input = AppTextInput(hint_text="Пароль", password=True, height=dp(52))
        card.add_widget(self.email_input)
        card.add_widget(self.password_input)

        login_btn = AppButton(text="Войти", font_size=sp(20))
        login_btn.bind(on_release=self.submit_login)
        card.add_widget(login_btn)

        self.status_label = BodyLabel(
            center=True,
            color=COLORS["text_muted"],
            font_size=sp(12),
            text="Если аккаунта ещё нет, вернись и выбери регистрацию.",
        )
        card.add_widget(self.status_label)

        content.add_widget(Widget())
        content.add_widget(card)
        content.add_widget(Widget())

        root.add_widget(content)
        self.coin_badge = CoinBadge(pos_hint={"right": 0.965, "top": 0.96})
        root.add_widget(self.coin_badge)
        self.add_widget(root)

    def on_pre_enter(self, *_):
        self.coin_badge.refresh_from_session()
        self.password_input.text = ""
        self.status_label.color = COLORS["text_muted"]
        if has_profiles():
            self.status_label.text = "Введи почту и пароль от сохранённого профиля."
        else:
            self.status_label.text = "Пока нет зарегистрированных профилей. Сначала создай аккаунт."

    def submit_login(self, *_):
        try:
            profile = login_profile(self.email_input.text, self.password_input.text)
        except ValueError as error:
            self.status_label.color = COLORS["error"]
            self.status_label.text = str(error)
            return

        app = App.get_running_app()
        if app is not None:
            app.sign_in(profile)

        self.password_input.text = ""
        self.status_label.color = COLORS["success"]
        self.status_label.text = f"Вход выполнен. Привет, {profile.name}."
        self.manager.current = "start"
