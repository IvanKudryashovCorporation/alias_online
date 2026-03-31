from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from services import (
    cancel_registration_verification,
    confirm_registration_verification_code,
    get_registration_verification_state,
    resend_registration_verification_code,
    save_profile,
)
from ui import (
    AppButton,
    AppTextInput,
    BodyLabel,
    BrandTitle,
    CoinBadge,
    COLORS,
    PixelLabel,
    RoundedPanel,
    ScreenBackground,
    register_game_font,
)


class EmailVerificationScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        register_game_font()
        self.verification_session_id = None
        self._ticker_event = None

        root = ScreenBackground()

        content = BoxLayout(
            orientation="vertical",
            spacing=dp(10),
            padding=[dp(18), dp(18), dp(18), dp(18)],
        )

        top_bar = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48))
        back_btn = AppButton(text="Назад", compact=True, size_hint=(None, None), size=(dp(128), dp(46)))
        back_btn.bind(on_release=self._go_back_to_registration)
        top_bar.add_widget(back_btn)
        top_bar.add_widget(Widget())
        content.add_widget(top_bar)

        content.add_widget(BrandTitle(text="ALIAS ONLINE", height=dp(128), font_size=sp(42), shadow_step=dp(3)))

        card = RoundedPanel(
            orientation="vertical",
            padding=[dp(16), dp(16), dp(16), dp(16)],
            spacing=dp(10),
            size_hint_y=None,
            height=dp(388),
        )
        card.add_widget(PixelLabel(text="Подтверждение e-mail", font_size=sp(20), center=True, size_hint_y=None, height=dp(30)))
        card.add_widget(
            BodyLabel(
                center=True,
                color=COLORS["text_muted"],
                font_size=sp(13),
                size_hint_y=None,
                height=dp(30),
                text="На твою почту отправлен 6-значный код.",
            )
        )
        self.email_hint = BodyLabel(
            center=True,
            color=COLORS["text_soft"],
            font_size=sp(13),
            size_hint_y=None,
            height=dp(24),
            text="",
        )
        card.add_widget(self.email_hint)

        self.code_input = AppTextInput(hint_text="Код из письма", height=dp(52), multiline=False)
        self.code_input.bind(text=self._sanitize_code_input)
        card.add_widget(self.code_input)

        self.timers_label = BodyLabel(
            center=True,
            color=COLORS["text_muted"],
            font_size=sp(12),
            size_hint_y=None,
            height=dp(24),
            text="",
        )
        card.add_widget(self.timers_label)

        verify_btn = AppButton(text="Подтвердить", font_size=sp(20))
        verify_btn.bind(on_release=self._confirm_code)
        card.add_widget(verify_btn)

        self.resend_btn = AppButton(text="Отправить код снова", compact=True, font_size=sp(16))
        self.resend_btn.bind(on_release=self._resend_code)
        card.add_widget(self.resend_btn)

        self.status_label = BodyLabel(
            center=True,
            color=COLORS["text_muted"],
            font_size=sp(12),
            text="Введи код из письма, чтобы завершить регистрацию.",
        )
        card.add_widget(self.status_label)

        content.add_widget(Widget())
        content.add_widget(card)
        content.add_widget(Widget())

        root.add_widget(content)
        self.coin_badge = CoinBadge(pos_hint={"right": 0.965, "top": 0.96})
        root.add_widget(self.coin_badge)
        self.add_widget(root)

    def start_verification(self, payload):
        self.verification_session_id = (payload or {}).get("session_id")
        self.code_input.text = ""
        self.status_label.color = COLORS["success"]
        self.status_label.text = "Код отправлен. Проверь почту и введи его ниже."
        self._refresh_state()

    def on_pre_enter(self, *_):
        self.coin_badge.refresh_from_session()
        app = App.get_running_app()
        if app is not None and getattr(app, "pending_registration_session_id", None):
            self.verification_session_id = app.pending_registration_session_id
        if not self.verification_session_id:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Сначала заполни регистрацию и запроси код."
            self.manager.current = "registration"
            return
        self._refresh_state()
        self._start_ticker()

    def on_leave(self, *_):
        self._stop_ticker()

    def _start_ticker(self):
        self._stop_ticker()
        self._ticker_event = Clock.schedule_interval(self._on_tick, 1.0)

    def _stop_ticker(self):
        if self._ticker_event is not None:
            self._ticker_event.cancel()
            self._ticker_event = None

    def _on_tick(self, *_):
        self._refresh_state()

    def _sanitize_code_input(self, *_):
        normalized = "".join(char for char in self.code_input.text if char.isdigit())[:6]
        if normalized != self.code_input.text:
            self.code_input.text = normalized

    def _format_seconds(self, value):
        total = max(0, int(value or 0))
        minutes, seconds = divmod(total, 60)
        if minutes:
            return f"{minutes}м {seconds:02d}с"
        return f"{seconds}с"

    def _refresh_state(self):
        if not self.verification_session_id:
            return
        try:
            state = get_registration_verification_state(self.verification_session_id)
        except ValueError as error:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = str(error)
            self.resend_btn.disabled = True
            self.timers_label.text = ""
            return

        self.email_hint.text = f"Код отправлен на: {state['masked_email']}"
        self.timers_label.text = (
            f"Код активен: {self._format_seconds(state['expires_in'])} • "
            f"Повторная отправка: {self._format_seconds(state['resend_in'])}"
        )
        self.resend_btn.disabled = state["resend_in"] > 0
        if state["resend_in"] > 0:
            self.resend_btn.text = f"Повтор через {self._format_seconds(state['resend_in'])}"
        else:
            self.resend_btn.text = "Отправить код снова"

    def _confirm_code(self, *_):
        if not self.verification_session_id:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Сессия подтверждения не найдена. Повтори регистрацию."
            return

        try:
            registration_payload = confirm_registration_verification_code(
                self.verification_session_id,
                self.code_input.text,
            )
            profile = save_profile(
                name=registration_payload["name"],
                email=registration_payload["email"],
                password=registration_payload["password"],
                avatar_path=registration_payload.get("avatar_path"),
                bio=registration_payload.get("bio"),
            )
        except ValueError as error:
            self.status_label.color = COLORS["error"]
            self.status_label.text = str(error)
            self._refresh_state()
            return

        app = App.get_running_app()
        if app is not None:
            app.sign_in(profile)
            app.clear_pending_registration_session()

        self.verification_session_id = None
        self.code_input.text = ""
        self.status_label.color = COLORS["success"]
        self.status_label.text = f"Почта подтверждена. Добро пожаловать, {profile.name}!"
        self.manager.current = "start"

    def _resend_code(self, *_):
        if not self.verification_session_id:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Сессия подтверждения не найдена. Повтори регистрацию."
            return

        try:
            resend_registration_verification_code(self.verification_session_id)
        except ValueError as error:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = str(error)
            return

        self.status_label.color = COLORS["success"]
        self.status_label.text = "Новый код отправлен на почту."
        self._refresh_state()

    def _go_back_to_registration(self, *_):
        if self.verification_session_id:
            cancel_registration_verification(self.verification_session_id)
        self.verification_session_id = None
        app = App.get_running_app()
        if app is not None:
            app.clear_pending_registration_session()
        self.manager.current = "registration"
