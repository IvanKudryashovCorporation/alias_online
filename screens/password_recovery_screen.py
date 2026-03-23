from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from services import (
    begin_password_reset,
    cancel_password_reset,
    confirm_password_reset_code,
    get_password_reset_state,
    resend_password_reset_code,
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


class PasswordRecoveryScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        register_game_font()

        self.return_screen = "login"
        self.reset_session_id = None
        self._ticker_event = None

        root = ScreenBackground()

        content = BoxLayout(
            orientation="vertical",
            spacing=dp(10),
            padding=[dp(18), dp(18), dp(18), dp(18)],
        )

        top_bar = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48))
        self.back_btn = AppButton(text="Назад", compact=True, size_hint=(None, None), size=(dp(128), dp(46)))
        self.back_btn.bind(on_release=self._go_back)
        top_bar.add_widget(self.back_btn)
        top_bar.add_widget(Widget())
        content.add_widget(top_bar)

        content.add_widget(BrandTitle(text="ALIAS ONLINE", height=dp(120), font_size=sp(40), shadow_step=dp(3)))

        card = RoundedPanel(
            orientation="vertical",
            padding=[dp(16), dp(16), dp(16), dp(16)],
            spacing=dp(10),
            size_hint_y=None,
            height=dp(500),
        )
        card.add_widget(PixelLabel(text="Восстановление пароля", center=True, font_size=sp(20), size_hint_y=None, height=dp(30)))
        card.add_widget(
            BodyLabel(
                center=True,
                color=COLORS["text_muted"],
                font_size=sp(13),
                size_hint_y=None,
                height=dp(28),
                text="Введи e-mail аккаунта. Мы отправим 6-значный код.",
            )
        )

        self.email_input = AppTextInput(hint_text="E-mail аккаунта", height=dp(52))
        card.add_widget(self.email_input)

        self.send_code_btn = AppButton(text="Отправить код", font_size=sp(18))
        self.send_code_btn.bind(on_release=self._request_reset_code)
        card.add_widget(self.send_code_btn)

        self.timers_label = BodyLabel(
            center=True,
            color=COLORS["text_muted"],
            font_size=sp(12),
            size_hint_y=None,
            height=dp(20),
            text="",
        )
        card.add_widget(self.timers_label)

        self.code_input = AppTextInput(hint_text="Код из письма", height=dp(48), multiline=False)
        self.code_input.bind(text=self._sanitize_code_input)
        card.add_widget(self.code_input)

        self.new_password_input = AppTextInput(hint_text="Новый пароль", password=True, height=dp(48), multiline=False)
        card.add_widget(self.new_password_input)

        self.apply_btn = AppButton(text="Изменить пароль", font_size=sp(18))
        self.apply_btn.bind(on_release=self._apply_new_password)
        card.add_widget(self.apply_btn)

        self.resend_btn = AppButton(text="Отправить код снова", compact=True, font_size=sp(15))
        self.resend_btn.bind(on_release=self._resend_code)
        card.add_widget(self.resend_btn)

        self.not_found_actions = BoxLayout(
            orientation="horizontal",
            spacing=dp(10),
            size_hint_y=None,
            height=0,
            opacity=0,
        )
        self.go_register_btn = AppButton(text="Создать аккаунт", compact=True, font_size=sp(14))
        self.go_login_btn = AppButton(text="Войти", compact=True, font_size=sp(14))
        self.go_register_btn.bind(on_release=lambda *_: setattr(self.manager, "current", "registration"))
        self.go_login_btn.bind(on_release=lambda *_: setattr(self.manager, "current", "login"))
        self.not_found_actions.add_widget(self.go_register_btn)
        self.not_found_actions.add_widget(self.go_login_btn)
        card.add_widget(self.not_found_actions)

        self.status_label = BodyLabel(
            center=True,
            color=COLORS["text_muted"],
            font_size=sp(12),
            text="",
        )
        card.add_widget(self.status_label)

        content.add_widget(Widget())
        content.add_widget(card)
        content.add_widget(Widget())

        root.add_widget(content)
        self.coin_badge = CoinBadge(pos_hint={"right": 0.965, "top": 0.96})
        root.add_widget(self.coin_badge)
        self.add_widget(root)

        self._toggle_code_stage(False)

    def start_flow(self, default_email="", return_screen="login"):
        self.return_screen = return_screen if return_screen else "login"
        self.email_input.text = (default_email or "").strip()
        self.code_input.text = ""
        self.new_password_input.text = ""
        self.status_label.color = COLORS["text_muted"]
        self.status_label.text = "Введи e-mail и получи код для восстановления пароля."
        self._show_not_found_actions(False)
        self._toggle_code_stage(False)

    def on_pre_enter(self, *_):
        self.coin_badge.refresh_from_session()
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
        if self.reset_session_id:
            self._refresh_reset_state()

    def _sanitize_code_input(self, *_):
        normalized = "".join(char for char in self.code_input.text if char.isdigit())[:6]
        if normalized != self.code_input.text:
            self.code_input.text = normalized

    def _show_not_found_actions(self, visible):
        self.not_found_actions.height = dp(42) if visible else 0
        self.not_found_actions.opacity = 1 if visible else 0
        self.not_found_actions.disabled = not visible

    def _toggle_code_stage(self, enabled):
        row_height = dp(48) if enabled else 0
        button_height = dp(50) if enabled else 0
        resend_height = dp(38) if enabled else 0

        self.code_input.height = row_height
        self.code_input.opacity = 1 if enabled else 0
        self.code_input.disabled = not enabled

        self.new_password_input.height = row_height
        self.new_password_input.opacity = 1 if enabled else 0
        self.new_password_input.disabled = not enabled

        self.apply_btn.height = button_height
        self.apply_btn.opacity = 1 if enabled else 0
        self.apply_btn.disabled = not enabled

        self.resend_btn.height = resend_height
        self.resend_btn.opacity = 1 if enabled else 0
        self.resend_btn.disabled = not enabled
        self.timers_label.opacity = 1 if enabled else 0

    def _format_seconds(self, value):
        total = max(0, int(value or 0))
        minutes, seconds = divmod(total, 60)
        if minutes:
            return f"{minutes}м {seconds:02d}с"
        return f"{seconds}с"

    def _refresh_reset_state(self):
        try:
            state = get_password_reset_state(self.reset_session_id)
        except ValueError as error:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = str(error)
            self._toggle_code_stage(False)
            self.reset_session_id = None
            self.timers_label.text = ""
            return

        self.timers_label.text = (
            f"Код активен: {self._format_seconds(state['expires_in'])} • "
            f"Повтор: {self._format_seconds(state['resend_in'])}"
        )
        self.resend_btn.disabled = state["resend_in"] > 0
        self.resend_btn.text = (
            f"Повтор через {self._format_seconds(state['resend_in'])}"
            if state["resend_in"] > 0
            else "Отправить код снова"
        )

    def _request_reset_code(self, *_):
        try:
            result = begin_password_reset(self.email_input.text)
        except ValueError as error:
            self.status_label.color = COLORS["error"]
            self.status_label.text = str(error)
            self._show_not_found_actions("не найден" in str(error).lower())
            return

        self.reset_session_id = result["session_id"]
        self._show_not_found_actions(False)
        self._toggle_code_stage(True)
        self.status_label.color = COLORS["success"]
        self.status_label.text = f"Код отправлен на {result['masked_email']}."
        self._refresh_reset_state()

    def _resend_code(self, *_):
        if not self.reset_session_id:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Сначала запроси код восстановления."
            return
        try:
            resend_password_reset_code(self.reset_session_id)
        except ValueError as error:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = str(error)
            return
        self.status_label.color = COLORS["success"]
        self.status_label.text = "Новый код отправлен."
        self._refresh_reset_state()

    def _apply_new_password(self, *_):
        if not self.reset_session_id:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Сначала запроси код восстановления."
            return
        try:
            confirm_password_reset_code(
                session_id=self.reset_session_id,
                code=self.code_input.text,
                new_password=self.new_password_input.text,
            )
        except ValueError as error:
            self.status_label.color = COLORS["error"]
            self.status_label.text = str(error)
            self._refresh_reset_state()
            return

        self.status_label.color = COLORS["success"]
        self.status_label.text = "Пароль успешно изменён. Теперь войди с новым паролем."
        self.code_input.text = ""
        self.new_password_input.text = ""
        cancel_password_reset(self.reset_session_id)
        self.reset_session_id = None
        self._toggle_code_stage(False)
        self.timers_label.text = ""
        self.manager.current = "login"

    def _go_back(self, *_):
        if self.reset_session_id:
            cancel_password_reset(self.reset_session_id)
            self.reset_session_id = None
        target = self.return_screen if self.return_screen in self.manager.screen_names else "login"
        self.manager.current = target
