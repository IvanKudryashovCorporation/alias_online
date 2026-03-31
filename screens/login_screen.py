from kivy.app import App
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from services import has_profiles, login_profile
from ui import (
    AppButton,
    AppTextInput,
    BodyLabel,
    BrandTitle,
    COLORS,
    PixelLabel,
    RoundedPanel,
    ScreenBackground,
    build_scrollable_content,
    register_game_font,
)


class LoginScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        register_game_font()

        root = ScreenBackground()
        scroll, content = build_scrollable_content(
            padding=[dp(18), dp(18), dp(18), dp(18)],
            spacing=12,
        )

        top_bar = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(50))
        back_btn = AppButton(text="Назад", compact=True, size_hint=(None, None), size=(dp(128), dp(46)))
        back_btn.bind(on_release=lambda *_: setattr(self.manager, "current", "entry"))
        top_bar.add_widget(back_btn)
        top_bar.add_widget(Widget())
        content.add_widget(top_bar)

        content.add_widget(BrandTitle(text="ALIAS ONLINE", height=dp(178), font_size=sp(60), shadow_step=dp(4)))

        card = RoundedPanel(
            orientation="vertical",
            padding=[dp(20), dp(20), dp(20), dp(18)],
            spacing=dp(12),
            size_hint_y=None,
            bg_color=COLORS["surface_card"],
        )
        card.bind(minimum_height=card.setter("height"))
        card._border_color.rgba = (1, 1, 1, 0.16)
        card._border_line.width = 1.2
        card.add_widget(PixelLabel(text="Вход", font_size=sp(31), center=True, size_hint_y=None, height=dp(40)))
        card.add_widget(
            BodyLabel(
                center=True,
                color=COLORS["text_muted"],
                font_size=sp(13.5),
                size_hint_y=None,
                text="Введи почту и пароль от сохранённого профиля",
            )
        )

        self.email_input = AppTextInput(hint_text="E-mail", height=dp(54))
        self.password_input = AppTextInput(hint_text="Пароль", password=True, height=dp(54))
        card.add_widget(self.email_input)
        card.add_widget(self.password_input)

        login_btn = AppButton(text="Войти", font_size=sp(21))
        login_btn.height = dp(72)
        login_btn.bind(on_release=self.submit_login)
        card.add_widget(login_btn)

        self.status_label = BodyLabel(
            center=True,
            color=COLORS["text_muted"],
            font_size=sp(11.5),
            text="Если аккаунта ещё нет, вернись и выбери регистрацию.",
            size_hint_y=None,
        )
        card.add_widget(self.status_label)

        forgot_password_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(28))
        forgot_password_row.add_widget(Widget())
        forgot_password_btn = AppButton(
            text="Забыли пароль?",
            compact=True,
            font_size=sp(10.5),
            size_hint=(None, None),
            size=(dp(124), dp(24)),
            button_color=(0.12, 0.17, 0.27, 0.42),
            pressed_color=(0.10, 0.15, 0.24, 0.58),
        )
        forgot_password_btn.bind(on_release=self.open_password_recovery)
        forgot_password_row.add_widget(forgot_password_btn)
        forgot_password_row.add_widget(Widget())
        card.add_widget(forgot_password_row)

        content.add_widget(card)
        content.add_widget(Widget(size_hint_y=None, height=dp(6)))

        root.add_widget(scroll)
        self.add_widget(root)

    def on_pre_enter(self, *_):
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

    def open_password_recovery(self, *_):
        recovery_screen = self.manager.get_screen("password_recovery")
        recovery_screen.start_flow(default_email=self.email_input.text, return_screen="login")
        self.manager.current = "password_recovery"
