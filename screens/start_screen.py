from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle, StencilPop, StencilPush, StencilUnUse, StencilUse
from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from ui import AvatarButton, AppButton, BodyLabel, BrandTitle, CoinBadge, COLORS, PixelLabel, RoundedPanel, ScreenBackground, register_game_font

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


class LegacyCoinBadge(RoundedPanel):
    def __init__(self, **kwargs):
        super().__init__(
            orientation="horizontal",
            spacing=dp(8),
            padding=[dp(12), dp(8), dp(12), dp(8)],
            size_hint=(None, None),
            size=(dp(122), dp(52)),
            bg_color=COLORS["surface"],
            shadow_alpha=0.22,
            **kwargs,
        )
        self.coin_icon = PixelLabel(text="C", font_size=sp(20), center=True, size_hint=(None, None))
        self.coin_icon.size = (dp(20), dp(20))
        self.add_widget(self.coin_icon)

        self.coin_value = PixelLabel(text="0", font_size=sp(18), center=False, size_hint_y=None)
        self.add_widget(self.coin_value)

    def set_value(self, value):
        self.coin_value.text = f"{int(value)} AC"


class StatTile(RoundedPanel):
    def __init__(self, title, **kwargs):
        super().__init__(
            orientation="vertical",
            spacing=dp(1),
            padding=[dp(8), dp(4), dp(8), dp(4)],
            size_hint=(None, None),
            size=(dp(118), dp(36)),
            bg_color=COLORS["surface_panel"],
            shadow_alpha=0.14,
            **kwargs,
        )
        self.title_label = BodyLabel(center=True, color=COLORS["text_muted"], font_size=sp(9), text=title)
        self.value_label = PixelLabel(center=True, font_size=sp(13), text="0")
        self.add_widget(self.title_label)
        self.add_widget(self.value_label)

    def set_value(self, value):
        self.value_label.text = str(value)


class ProfileSummaryCard(ButtonBehavior, RoundedPanel):
    def __init__(self, **kwargs):
        super().__init__(
            orientation="vertical",
            spacing=dp(4),
            padding=[dp(16), dp(8), dp(16), dp(8)],
            size_hint=(None, None),
            size=(dp(286), dp(202)),
            bg_color=COLORS["surface"],
            shadow_alpha=0.22,
            **kwargs,
        )

        avatar_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48))
        avatar_row.add_widget(Widget())
        self.avatar_button = AvatarButton()
        self.avatar_button.size = (dp(46), dp(46))
        avatar_row.add_widget(self.avatar_button)
        avatar_row.add_widget(Widget())
        self.add_widget(avatar_row)

        self.name_label = PixelLabel(center=True, font_size=sp(18), text="Профиль", size_hint_y=None)
        self.add_widget(self.name_label)

        self.meta_label = BodyLabel(center=True, color=COLORS["text_muted"], font_size=sp(10), text="", size_hint_y=None)
        self.add_widget(self.meta_label)

        first_row = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(36))
        self.games_tile = StatTile("Игр")
        self.earned_tile = StatTile("Заработано")
        first_row.add_widget(self.games_tile)
        first_row.add_widget(self.earned_tile)
        self.add_widget(first_row)

        second_row = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(36))
        self.guessed_tile = StatTile("Отгадано")
        self.explained_tile = StatTile("Объяснено")
        second_row.add_widget(self.guessed_tile)
        second_row.add_widget(self.explained_tile)
        self.add_widget(second_row)

    def on_press(self):
        self.opacity = 0.9

    def on_release(self):
        self.opacity = 1

    def set_guest(self, guest_name):
        self.avatar_button.set_profile(None)
        self.name_label.text = guest_name or "Гость"
        self.meta_label.text = "Гостевой режим"
        self.games_tile.set_value(0)
        self.earned_tile.set_value(0)
        self.guessed_tile.set_value(0)
        self.explained_tile.set_value(0)

    def set_profile(self, profile, player_name=None):
        self.avatar_button.set_profile(profile)
        if profile is None:
            self.set_guest(player_name or "Профиль")
            return

        self.name_label.text = player_name or profile.name
        self.meta_label.text = f"Код игрока #{profile.id}"
        self.games_tile.set_value(profile.games_played)
        self.earned_tile.set_value(profile.total_points)
        self.guessed_tile.set_value(profile.guessed_words)
        self.explained_tile.set_value(profile.explained_words)


class StartScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        register_game_font()
        self.guest_access_popup = None
        self.support_popup = None
        self.room_access_popup = None
        self.room_access_popup_message_label = None
        self.room_access_popup_action_label = ""
        self._room_access_event = None

        root = ScreenBackground()

        self.support_button = SupportIconButton(pos_hint={"x": 0.04, "top": 0.957})
        self.support_button.bind(on_release=self._open_support_popup)

        self.coin_badge = CoinBadge(pos_hint={"right": 0.965, "top": 0.96})

        self.profile_card = ProfileSummaryCard()
        self.profile_card.bind(on_release=self._on_profile_pressed)
        self.profile_card.avatar_button.bind(on_release=self._on_profile_pressed)

        content = BoxLayout(
            orientation="vertical",
            spacing=dp(6),
            padding=[dp(20), dp(24), dp(20), dp(18)],
        )

        content.add_widget(Widget(size_hint_y=None, height=dp(10)))
        content.add_widget(BrandTitle(height=dp(212), font_size=sp(56)))

        profile_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(210))
        profile_row.add_widget(Widget())
        profile_row.add_widget(self.profile_card)
        profile_row.add_widget(Widget())
        content.add_widget(profile_row)
        content.add_widget(Widget(size_hint_y=None, height=dp(8)))

        menu_holder = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(308),
            spacing=dp(12),
        )

        create_btn = AppButton(text="Создать комнату", font_size=sp(22))
        join_btn = AppButton(text="Войти в комнату", font_size=sp(22))
        friends_btn = AppButton(text="Друзья", font_size=sp(22))
        rules_btn = AppButton(text="Правила", font_size=sp(22))
        self.create_room_btn = create_btn
        self.join_room_btn = join_btn

        for button in (create_btn, join_btn, friends_btn, rules_btn):
            button.height = dp(68)
            menu_holder.add_widget(button)

        create_btn.bind(on_release=self._handle_create_room_press)
        join_btn.bind(on_release=self._handle_join_room_press)
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
        root.add_widget(self.coin_badge)
        root.add_widget(self.version_label)
        self.add_widget(root)

    def on_pre_enter(self, *_):
        self.refresh_profile()
        self._refresh_room_access_ui()
        self._start_room_access_watch()

    def on_leave(self, *_):
        self._stop_room_access_watch()
        self._dismiss_room_access_popup()
        self._dismiss_guest_access_popup()
        self._dismiss_support_popup()

    def refresh_profile(self):
        app = App.get_running_app()
        player_name = app.resolve_player_name() if app is not None else ""

        if app is not None and getattr(app, "guest_mode", False):
            self.profile_card.set_guest(player_name or "Гость")
            self.coin_badge.set_value(0)
            return

        profile = app.current_profile() if app is not None else None
        self.profile_card.set_profile(profile, player_name=player_name or "")
        self.coin_badge.set_value(getattr(profile, "alias_coins", 0) if profile is not None else 0)

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

    def _start_room_access_watch(self):
        self._stop_room_access_watch()
        self._room_access_event = Clock.schedule_interval(lambda _dt: self._refresh_room_access_ui(), 1.0)

    def _stop_room_access_watch(self):
        if self._room_access_event is not None:
            self._room_access_event.cancel()
            self._room_access_event = None

    def _set_room_button_locked(self, button, locked):
        if button is None:
            return
        if locked:
            button._rest_button_color = COLORS["danger_button"]
            button._pressed_button_color = COLORS["danger_button_pressed"]
            button._border_color.rgba = (1, 0.82, 0.82, 0.30)
        else:
            button._rest_button_color = COLORS["button"]
            button._pressed_button_color = COLORS["button_pressed"]
            button._border_color.rgba = COLORS["outline"]
        button._button_color.rgba = button._rest_button_color

    def _refresh_room_access_ui(self):
        app = App.get_running_app()
        room_access_state = app.room_access_state() if app is not None and hasattr(app, "room_access_state") else {"active": False}
        locked = bool(room_access_state.get("active"))
        self._set_room_button_locked(self.create_room_btn, locked)
        self._set_room_button_locked(self.join_room_btn, locked)
        self._update_room_access_popup_message(room_access_state)

    def _update_room_access_popup_message(self, room_access_state=None):
        if self.room_access_popup is None or self.room_access_popup_message_label is None:
            return

        app = App.get_running_app()
        if room_access_state is None:
            room_access_state = app.room_access_state() if app is not None and hasattr(app, "room_access_state") else {"active": False}

        if not bool(room_access_state.get("active")):
            self._dismiss_room_access_popup()
            return

        if app is not None and hasattr(app, "format_room_access_message"):
            self.room_access_popup_message_label.text = app.format_room_access_message(
                self.room_access_popup_action_label or "Доступ к комнатам"
            )
            return

        remaining_seconds = max(0, int(room_access_state.get("remaining_seconds") or 0))
        minutes, seconds = divmod(remaining_seconds, 60)
        eta = f"{minutes:02d}:{seconds:02d}" if minutes > 0 else f"{seconds} сек"
        self.room_access_popup_message_label.text = (
            "Доступ к комнатам временно закрыт.\n"
            f"Осталось подождать: {eta}."
        )

    def _open_room_access_popup(self, action_label):
        self._dismiss_room_access_popup()

        app = App.get_running_app()
        message = app.format_room_access_message(action_label) if app is not None and hasattr(app, "format_room_access_message") else "Доступ к комнатам временно закрыт."
        self.room_access_popup_action_label = action_label

        body = BoxLayout(
            orientation="vertical",
            spacing=dp(12),
            padding=[dp(16), dp(16), dp(16), dp(16)],
        )
        panel = RoundedPanel(
            orientation="vertical",
            spacing=dp(12),
            padding=[dp(18), dp(18), dp(18), dp(18)],
            size_hint_y=None,
            height=dp(272),
        )
        panel.add_widget(PixelLabel(text="Доступ к комнатам закрыт", font_size=sp(18), center=True, size_hint_y=None))

        warning_card = RoundedPanel(
            orientation="vertical",
            spacing=dp(6),
            padding=[dp(14), dp(12), dp(14), dp(12)],
            size_hint_y=None,
            height=dp(118),
            bg_color=(0.29, 0.11, 0.11, 0.92),
            shadow_alpha=0.14,
        )
        warning_card._border_color.rgba = COLORS["error"]
        warning_card._border_line.width = 1.6
        self.room_access_popup_message_label = BodyLabel(
            center=True,
            color=COLORS["warning"],
            font_size=sp(11.5),
            text=message,
            size_hint_y=None,
        )
        warning_card.add_widget(
            self.room_access_popup_message_label
        )
        panel.add_widget(warning_card)

        close_btn = AppButton(text="Хорошо", compact=True, font_size=sp(15))
        close_btn.height = dp(46)
        close_btn.bind(on_release=lambda *_: self._dismiss_room_access_popup())
        panel.add_widget(close_btn)
        body.add_widget(panel)

        self.room_access_popup = Popup(
            title="",
            separator_height=0,
            auto_dismiss=True,
            background="atlas://data/images/defaulttheme/modalview-background",
            content=body,
            size_hint=(0.82, None),
            height=dp(320),
        )
        self.room_access_popup.bind(on_dismiss=self._on_room_access_popup_dismiss)
        self.room_access_popup.open()
        self._update_room_access_popup_message()

    def _on_room_access_popup_dismiss(self, *_):
        self.room_access_popup = None
        self.room_access_popup_message_label = None
        self.room_access_popup_action_label = ""

    def _dismiss_room_access_popup(self):
        if self.room_access_popup is not None:
            popup = self.room_access_popup
            self.room_access_popup = None
            self.room_access_popup_message_label = None
            self.room_access_popup_action_label = ""
            popup.dismiss()

    def _handle_create_room_press(self, *_):
        app = App.get_running_app()
        room_access_state = app.room_access_state() if app is not None and hasattr(app, "room_access_state") else {"active": False}
        if room_access_state.get("active"):
            self._open_room_access_popup("Создание комнаты")
            return
        self.manager.current = "create_room"

    def _handle_join_room_press(self, *_):
        app = App.get_running_app()
        room_access_state = app.room_access_state() if app is not None and hasattr(app, "room_access_state") else {"active": False}
        if room_access_state.get("active"):
            self._open_room_access_popup("Вход в комнату")
            return
        self.manager.current = "join_room"

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
