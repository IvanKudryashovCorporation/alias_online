from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
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
        self._window = Window

        root = ScreenBackground()

        content = BoxLayout(
            orientation="vertical",
            spacing=dp(12),
            padding=[dp(18), dp(16), dp(18), dp(18)],
        )
        self._content_layout = content

        self._top_spacer = Widget(size_hint_y=None, height=dp(4))
        content.add_widget(self._top_spacer)

        self.brand_title = BrandTitle(height=dp(338), font_size=sp(84), shadow_step=dp(5))
        content.add_widget(self.brand_title)

        mode_hint_card = RoundedPanel(
            orientation="vertical",
            size_hint_y=None,
            height=dp(64),
            padding=[dp(14), dp(10), dp(14), dp(10)],
            bg_color=(0.11, 0.19, 0.30, 0.80),
        )
        mode_hint_card._border_color.rgba = (0.99, 0.95, 0.36, 0.32)
        mode_hint_card._border_line.width = 1.4
        self.mode_hint_card = mode_hint_card

        self.mode_hint_label = BodyLabel(
            center=True,
            color=COLORS["accent"],
            font_size=sp(18),
            size_hint=(1, 1),
            auto_height=False,
            text="Выбери, как хочешь начать игру",
        )
        self.mode_hint_label.bind(size=self._sync_mode_hint_text)
        mode_hint_card.add_widget(self.mode_hint_label)
        content.add_widget(mode_hint_card)

        self.menu_card = RoundedPanel(
            orientation="vertical",
            padding=[dp(18), dp(18), dp(18), dp(18)],
            spacing=dp(12),
            size_hint_y=None,
            height=dp(316),
            bg_color=COLORS["surface_card"],
        )
        self.menu_card._border_color.rgba = (1, 1, 1, 0.16)
        self.menu_card._border_line.width = 1.3

        login_btn = AppButton(text="Войти", font_size=sp(22))
        register_btn = AppButton(text="Зарегистрироваться", font_size=sp(22))
        login_btn.height = dp(80)
        register_btn.height = dp(80)
        self.menu_card.add_widget(login_btn)
        self.menu_card.add_widget(register_btn)
        self._guest_offset_spacer = Widget(size_hint_y=None, height=dp(10))
        self.menu_card.add_widget(self._guest_offset_spacer)

        guest_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(46))
        guest_row.add_widget(Widget())
        guest_btn = AppButton(
            text="Играть как гость",
            compact=True,
            font_size=sp(13),
            size_hint=(None, None),
            size=(dp(192), dp(36)),
            button_color=(0.10, 0.16, 0.26, 0.62),
            pressed_color=(0.09, 0.14, 0.23, 0.76),
        )
        guest_row.add_widget(guest_btn)
        guest_row.add_widget(Widget())
        self.menu_card.add_widget(guest_row)

        hint = BodyLabel(
            center=True,
            color=COLORS["text_muted"],
            font_size=sp(10.5),
            size_hint_y=None,
            text="Гость может играть сразу, а профиль откроет сохранение статистики.",
        )
        self.menu_card.add_widget(hint)

        login_btn.bind(on_release=lambda *_: setattr(self.manager, "current", "login"))
        register_btn.bind(on_release=self._go_to_registration)
        guest_btn.bind(on_release=self._play_as_guest)

        content.add_widget(self.menu_card)
        content.add_widget(Widget())

        root.add_widget(content)
        self.add_widget(root)

        self.bind(size=self._schedule_responsive_layout)
        if self._window is not None:
            self._window.bind(size=self._schedule_responsive_layout)
        Clock.schedule_once(self._apply_responsive_layout, 0)

    def _sync_mode_hint_text(self, *_):
        self.mode_hint_label.text_size = (
            max(0, self.mode_hint_label.width),
            max(0, self.mode_hint_label.height),
        )

    def _schedule_responsive_layout(self, *_):
        Clock.unschedule(self._apply_responsive_layout)
        Clock.schedule_once(self._apply_responsive_layout, 0)

    def _apply_responsive_layout(self, *_):
        viewport_width = float(self.width or 0)
        viewport_height = float(self.height or 0)
        if (viewport_width <= 0 or viewport_height <= 0) and self._window is not None:
            viewport_width, viewport_height = self._window.size
        if viewport_width <= 0 or viewport_height <= 0:
            return

        compact = viewport_width < dp(390) or viewport_height < dp(780)
        medium = viewport_width < dp(440) or viewport_height < dp(880)

        self._content_layout.padding = [
            dp(14 if compact else 18),
            dp(12 if compact else 16),
            dp(14 if compact else 18),
            dp(14 if compact else 18),
        ]
        self._content_layout.spacing = dp(9 if compact else 11 if medium else 12)

        self._top_spacer.height = dp(2 if compact else 4)

        self.brand_title.height = dp(236 if compact else 292 if medium else 338)
        self.brand_title.set_style(
            font_size=sp(70 if compact else 78 if medium else 84),
            shadow_step=dp(4 if compact else 5),
        )

        self.mode_hint_card.height = dp(66 if compact else 64 if medium else 62)
        self.mode_hint_card.padding = [
            dp(12 if compact else 14),
            dp(9 if compact else 10),
            dp(12 if compact else 14),
            dp(9 if compact else 10),
        ]
        self.mode_hint_label.font_size = sp(15.5 if compact else 17 if medium else 18)
        self._sync_mode_hint_text()

        self.menu_card.height = dp(308 if compact else 322 if medium else 336)
        self.menu_card.padding = [
            dp(14 if compact else 18),
            dp(14 if compact else 18),
            dp(14 if compact else 18),
            dp(14 if compact else 18),
        ]
        self._guest_offset_spacer.height = dp(8 if compact else 10 if medium else 12)

    def _go_to_registration(self, *_):
        app = App.get_running_app()
        if self.manager is not None:
            self.manager.current = "registration"
        if app is not None:
            Clock.schedule_once(lambda *_: app.start_registration_flow(), 0)

    def _play_as_guest(self, *_):
        app = App.get_running_app()
        if app is not None:
            app.enter_guest_mode()
        self.manager.current = "start"
