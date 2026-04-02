from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle, StencilPop, StencilPush, StencilUnUse, StencilUse
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from ui import AvatarButton, AppButton, BodyLabel, BrandTitle, CoinBadge, COLORS, PixelLabel, RoundedPanel, ScreenBackground, register_game_font

APP_VERSION = "1.1.0"


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
        self._base_size = (dp(126), dp(42))
        self._base_padding = [dp(8), dp(5), dp(8), dp(5)]
        self._base_spacing = dp(2)
        self._base_title_font_size = sp(9.2)
        self._base_value_font_size = sp(14)
        super().__init__(
            orientation="vertical",
            spacing=self._base_spacing,
            padding=list(self._base_padding),
            size_hint=(None, None),
            size=self._base_size,
            bg_color=COLORS["surface_panel"],
            shadow_alpha=0.14,
            **kwargs,
        )
        self.title_label = BodyLabel(center=True, color=COLORS["text_muted"], font_size=self._base_title_font_size, text=title)
        self.value_label = PixelLabel(center=True, font_size=self._base_value_font_size, text="0")
        self.add_widget(self.title_label)
        self.add_widget(self.value_label)
        self.set_density(1.0)

    def set_value(self, value):
        self.value_label.text = str(value)

    def set_density(self, scale):
        density = max(0.72, min(1.0, float(scale)))
        self.size = (self._base_size[0] * density, self._base_size[1] * density)
        self.padding = [part * density for part in self._base_padding]
        self.spacing = self._base_spacing * density
        self.title_label.font_size = self._base_title_font_size * density
        self.value_label.font_size = self._base_value_font_size * density


class ProfileSummaryCard(ButtonBehavior, RoundedPanel):
    def __init__(self, **kwargs):
        self._base_padding = [dp(16), dp(10), dp(16), dp(10)]
        self._base_spacing = dp(6)
        self._base_avatar_row_height = dp(62)
        self._base_avatar_size = dp(58)
        self._base_name_font_size = sp(20)
        self._base_meta_font_size = sp(11.5)
        self._base_stats_row_height = dp(42)
        self._base_stats_row_spacing = dp(8)
        super().__init__(
            orientation="vertical",
            spacing=self._base_spacing,
            padding=list(self._base_padding),
            size_hint=(None, None),
            size=(dp(330), dp(260)),
            bg_color=COLORS["surface"],
            shadow_alpha=0.22,
            **kwargs,
        )

        avatar_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=self._base_avatar_row_height)
        avatar_row.add_widget(Widget())
        self.avatar_button = AvatarButton()
        self.avatar_button.size = (self._base_avatar_size, self._base_avatar_size)
        avatar_row.add_widget(self.avatar_button)
        avatar_row.add_widget(Widget())
        self.add_widget(avatar_row)
        self._avatar_row = avatar_row

        self.name_label = PixelLabel(center=True, font_size=sp(20), text="Профиль", size_hint_y=None)
        self.add_widget(self.name_label)

        self.meta_label = BodyLabel(center=True, color=COLORS["text_muted"], font_size=sp(11.5), text="", size_hint_y=None)
        self.add_widget(self.meta_label)

        first_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(42))
        first_row.add_widget(Widget())
        first_row_inner = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint=(None, 1))
        self.games_tile = StatTile("Игр")
        self.earned_tile = StatTile("Заработано")
        first_row_inner.add_widget(self.games_tile)
        first_row_inner.add_widget(self.earned_tile)
        first_row.add_widget(first_row_inner)
        first_row.add_widget(Widget())
        self.add_widget(first_row)
        self._first_stats_row_inner = first_row_inner
        self._first_stats_row = first_row

        second_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(42))
        second_row.add_widget(Widget())
        second_row_inner = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint=(None, 1))
        self.guessed_tile = StatTile("Отгадано")
        self.explained_tile = StatTile("Объяснено")
        second_row_inner.add_widget(self.guessed_tile)
        second_row_inner.add_widget(self.explained_tile)
        second_row.add_widget(second_row_inner)
        second_row.add_widget(Widget())
        self.add_widget(second_row)
        self._second_stats_row_inner = second_row_inner
        self._second_stats_row = second_row
        self.set_density(1.0)

    def on_press(self):
        self.opacity = 0.9

    def on_release(self):
        self.opacity = 1

    def set_density(self, scale):
        density = max(0.72, min(1.0, float(scale)))
        self.padding = [part * density for part in self._base_padding]
        self.spacing = self._base_spacing * density
        self._avatar_row.height = self._base_avatar_row_height * density
        avatar_side = self._base_avatar_size * density
        self.avatar_button.size = (avatar_side, avatar_side)
        self.name_label.font_size = self._base_name_font_size * density
        self.meta_label.font_size = self._base_meta_font_size * density
        self._first_stats_row.height = self._base_stats_row_height * density
        self._second_stats_row.height = self._base_stats_row_height * density
        row_spacing = self._base_stats_row_spacing * density
        self._first_stats_row_inner.spacing = row_spacing
        self._second_stats_row_inner.spacing = row_spacing
        for tile in (self.games_tile, self.earned_tile, self.guessed_tile, self.explained_tile):
            tile.set_density(density)
        inner_width = self.games_tile.width + self.earned_tile.width + row_spacing
        self._first_stats_row_inner.width = inner_width
        self._second_stats_row_inner.width = inner_width

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
        self._window = Window

        root = ScreenBackground()

        self.support_button = SupportIconButton(pos_hint={"x": 0.04, "top": 0.957})
        self.support_button.bind(on_release=self._open_support_popup)

        self.coin_badge = CoinBadge(pos_hint={"right": 0.965, "top": 0.96})

        self.profile_card = ProfileSummaryCard()
        self.profile_card.bind(on_release=self._on_profile_pressed)
        self.profile_card.avatar_button.bind(on_release=self._on_profile_pressed)

        content = BoxLayout(
            orientation="vertical",
            spacing=dp(11),
            padding=[dp(18), dp(16), dp(18), dp(16)],
        )
        self._content_layout = content

        self._top_spacer = Widget(size_hint_y=None, height=dp(4))
        content.add_widget(self._top_spacer)
        self.brand_title = BrandTitle(height=dp(270), font_size=sp(76), shadow_step=dp(4))
        content.add_widget(self.brand_title)

        subtitle_card = RoundedPanel(
            orientation="vertical",
            size_hint_y=None,
            height=dp(44),
            padding=[dp(12), dp(8), dp(12), dp(8)],
            bg_color=(0.11, 0.18, 0.29, 0.70),
        )
        subtitle_card._border_color.rgba = (0.99, 0.95, 0.36, 0.22)
        subtitle_card._border_line.width = 1.2
        subtitle_card.add_widget(
            BodyLabel(
                center=True,
                color=COLORS["accent"],
                font_size=sp(15),
                size_hint_y=None,
                text="Выбери режим и заходи в матч",
            )
        )
        self.subtitle_card = subtitle_card
        self.subtitle_label = subtitle_card.children[0] if subtitle_card.children else None
        content.add_widget(subtitle_card)

        profile_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(264))
        profile_row.add_widget(Widget())
        profile_row.add_widget(self.profile_card)
        profile_row.add_widget(Widget())
        self.profile_row = profile_row
        content.add_widget(profile_row)
        self._profile_gap_spacer = Widget(size_hint_y=None, height=dp(6))
        content.add_widget(self._profile_gap_spacer)

        menu_holder = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing=dp(13),
            padding=[0, dp(4), 0, dp(4)],
        )
        self.menu_holder = menu_holder

        create_btn = AppButton(text="Создать комнату", font_size=sp(23))
        join_btn = AppButton(text="Войти в комнату", font_size=sp(23))
        friends_btn = AppButton(text="Друзья", font_size=sp(23))
        rules_btn = AppButton(text="Правила", font_size=sp(23))
        self.create_room_btn = create_btn
        self.join_room_btn = join_btn

        for button in (create_btn, join_btn, friends_btn, rules_btn):
            button.height = dp(84)
            menu_holder.add_widget(button)
        self._menu_buttons = (create_btn, join_btn, friends_btn, rules_btn)
        self.menu_holder.height = sum(button.height for button in self._menu_buttons) + menu_holder.spacing * (len(self._menu_buttons) - 1) + menu_holder.padding[1] + menu_holder.padding[3]

        create_btn.bind(on_release=self._handle_create_room_press)
        join_btn.bind(on_release=self._handle_join_room_press)
        friends_btn.bind(on_release=self._open_friends_screen)
        rules_btn.bind(on_release=self._open_rules_screen)

        content.add_widget(menu_holder)

        self.version_label = BodyLabel(
            center=True,
            size_hint=(None, None),
            size=(dp(168), dp(18)),
            pos_hint={"center_x": 0.5, "y": 0.001},
            font_size=sp(10.5),
            color=COLORS["text_muted"],
            text=f"Версия {APP_VERSION}",
        )

        root.add_widget(content)
        root.add_widget(self.support_button)
        root.add_widget(self.coin_badge)
        root.add_widget(self.version_label)
        self.add_widget(root)
        self.bind(size=self._schedule_responsive_layout)
        if self._window is not None:
            self._window.bind(size=self._schedule_responsive_layout)
        Clock.schedule_once(self._apply_responsive_layout, 0)

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

        compact = viewport_width < dp(390) or viewport_height < dp(760)
        medium = viewport_width < dp(440) or viewport_height < dp(860)

        base_top_padding = dp(10 if compact else 14 if medium else 16)
        base_bottom_padding = dp(16 if compact else 18 if medium else 20)
        side_padding = dp(14 if compact else 18)
        base_spacing = dp(8 if compact else 10 if medium else 11)
        base_title_height = dp(170 if compact else 220 if medium else 270)
        base_title_font = sp(62 if compact else 70 if medium else 76)
        base_shadow = dp(3 if compact else 4)
        base_top_spacer = dp(2 if compact else 4)
        base_subtitle_height = dp(40 if compact else 44)
        base_subtitle_font = sp(13 if compact else 14 if medium else 15)
        base_profile_height = dp(236 if compact else 250 if medium else 260)
        base_profile_gap = dp(3 if compact else 6)
        base_menu_spacing = dp(9 if compact else 11 if medium else 13)
        base_button_height = dp(66 if compact else 74 if medium else 84)
        base_button_font = sp(19 if compact else 21 if medium else 23)
        base_menu_padding_vertical = dp(4)

        menu_count = len(self._menu_buttons)
        menu_height_base = (
            base_button_height * menu_count
            + base_menu_spacing * max(0, menu_count - 1)
            + base_menu_padding_vertical * 2
        )
        base_required_height = (
            base_top_padding
            + base_bottom_padding
            + base_top_spacer
            + base_title_height
            + base_subtitle_height
            + (base_profile_height + dp(8))
            + base_profile_gap
            + menu_height_base
            + base_spacing * 5
        )
        usable_height = max(dp(560), viewport_height - dp(22))
        vertical_scale = max(0.72, min(1.0, usable_height / max(base_required_height, 1)))

        top_padding = base_top_padding * vertical_scale
        bottom_padding = base_bottom_padding * vertical_scale
        spacing = max(dp(6), base_spacing * vertical_scale)
        self._content_layout.padding = [side_padding, top_padding, side_padding, bottom_padding]
        self._content_layout.spacing = spacing

        title_height = base_title_height * vertical_scale
        title_font = max(sp(42), base_title_font * vertical_scale)
        shadow = max(dp(2.4), base_shadow * vertical_scale)
        self.brand_title.height = title_height
        self.brand_title.set_style(font_size=title_font, shadow_step=shadow)
        self._top_spacer.height = base_top_spacer * vertical_scale

        self.subtitle_card.height = base_subtitle_height * vertical_scale
        if self.subtitle_label is not None:
            self.subtitle_label.font_size = max(sp(11.8), base_subtitle_font * vertical_scale)

        available_profile_width = max(dp(236), viewport_width - side_padding * 2 - dp(14))
        profile_width = min(dp(330), available_profile_width)
        width_density = max(0.72, min(1.0, profile_width / dp(330)))
        card_density = min(width_density, vertical_scale)
        self.profile_card.set_density(card_density)
        self.profile_card.width = profile_width
        self.profile_card.height = base_profile_height * vertical_scale
        self.profile_row.height = self.profile_card.height + dp(8) * vertical_scale
        self._profile_gap_spacer.height = base_profile_gap * vertical_scale

        menu_spacing = base_menu_spacing * vertical_scale
        menu_padding_vertical = base_menu_padding_vertical * vertical_scale
        self.menu_holder.spacing = menu_spacing
        self.menu_holder.padding = [0, menu_padding_vertical, 0, menu_padding_vertical]

        for button in self._menu_buttons:
            button.height = base_button_height * vertical_scale
            button.font_size = max(sp(17), base_button_font * vertical_scale)

        self.menu_holder.height = (
            sum(button.height for button in self._menu_buttons)
            + self.menu_holder.spacing * max(0, menu_count - 1)
            + self.menu_holder.padding[1]
            + self.menu_holder.padding[3]
        )

        support_size = dp(48 if compact else 52)
        badge_scale = 0.92 if compact else 1.0
        overlay_top = 0.968 if compact else 0.96
        self.support_button.size = (support_size, support_size)
        self.support_button.pos_hint = {"x": 0.03 if compact else 0.04, "top": overlay_top}
        self.coin_badge.size = (dp(122) * badge_scale, dp(52) * badge_scale)
        self.coin_badge.pos_hint = {"right": 0.968, "top": overlay_top}

        self.version_label.font_size = max(sp(9.6), sp(9.8 if compact else 10.2 if medium else 10.5) * vertical_scale)
        self.version_label.pos_hint = {"center_x": 0.5, "y": 0.001}

    def on_pre_enter(self, *_):
        self._schedule_responsive_layout()
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
            self.coin_badge.refresh_from_session()
            return

        profile = app.current_profile() if app is not None else None
        self.profile_card.set_profile(profile, player_name=player_name or "")
        self.coin_badge.refresh_from_session()

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
            spacing=dp(8),
            padding=[dp(12), dp(12), dp(12), dp(12)],
        )

        panel = RoundedPanel(
            orientation="vertical",
            spacing=dp(10),
            padding=[dp(16), dp(16), dp(16), dp(16)],
            size_hint_y=None,
            shadow_alpha=0.2,
        )
        panel.height = dp(328)
        panel.bind(minimum_height=panel.setter("height"))
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

        close_btn = AppButton(
            text="Закрыть",
            compact=True,
            font_size=sp(14),
            button_color=(0.17, 0.22, 0.34, 0.88),
            pressed_color=(0.15, 0.19, 0.30, 0.94),
        )
        close_btn.height = dp(44)
        close_btn.bind(on_release=lambda *_: self._dismiss_guest_access_popup())
        panel.add_widget(close_btn)

        body.add_widget(panel)

        self.guest_access_popup = Popup(
            title="",
            title_size=0,
            separator_height=0,
            auto_dismiss=True,
            background="",
            background_color=(0, 0, 0, 0),
            content=body,
            size_hint=(0.84, None),
            height=dp(352),
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
            spacing=dp(8),
            padding=[dp(12), dp(12), dp(12), dp(12)],
        )

        panel = RoundedPanel(
            orientation="vertical",
            spacing=dp(10),
            padding=[dp(16), dp(16), dp(16), dp(16)],
            size_hint_y=None,
            shadow_alpha=0.2,
        )
        panel.height = dp(232)
        panel.bind(minimum_height=panel.setter("height"))
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
            title_size=0,
            separator_height=0,
            auto_dismiss=True,
            background="",
            background_color=(0, 0, 0, 0),
            content=body,
            size_hint=(0.78, None),
            height=dp(248),
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
            background="",
            background_color=(0, 0, 0, 0),
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
        if app is not None and hasattr(app, "ensure_screen"):
            app.ensure_screen("create_room")
        self.manager.current = "create_room"

    def _handle_join_room_press(self, *_):
        app = App.get_running_app()
        room_access_state = app.room_access_state() if app is not None and hasattr(app, "room_access_state") else {"active": False}
        if room_access_state.get("active"):
            self._open_room_access_popup("Вход в комнату")
            return
        if app is not None and hasattr(app, "ensure_screen"):
            app.ensure_screen("join_room")
        self.manager.current = "join_room"

    def _open_friends_screen(self, *_):
        app = App.get_running_app()
        if app is not None and hasattr(app, "ensure_screen"):
            app.ensure_screen("friends")
        self.manager.current = "friends"

    def _open_rules_screen(self, *_):
        app = App.get_running_app()
        if app is not None and hasattr(app, "ensure_screen"):
            app.ensure_screen("rules")
        self.manager.current = "rules"

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
