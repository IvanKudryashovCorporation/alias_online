import random
import string
from threading import Thread
from types import SimpleNamespace

from kivy.app import App
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from services import (
    ROOM_CREATION_COST,
    create_online_room,
    generate_room_code_preview,
    join_online_room,
    spend_alias_coins,
)
from ui import (
    AppButton,
    AppTextInput,
    BodyLabel,
    BrandTitle,
    CoinBadge,
    COLORS,
    LoadingOverlay,
    PixelLabel,
    RoundedPanel,
    ScreenBackground,
    build_scrollable_content,
    register_game_font,
)


class RoomTypeChip(AppButton):
    def __init__(self, text, scope, on_select, **kwargs):
        super().__init__(
            text=text,
            compact=True,
            font_size=sp(14),
            size_hint=(1, None),
            height=dp(46),
            button_color=(0.10, 0.16, 0.27, 0.92),
            pressed_color=(0.13, 0.22, 0.37, 0.96),
            **kwargs,
        )
        self.scope = scope
        self._on_select = on_select
        self._active = False
        self.bind(on_release=lambda *_: self._on_select(self.scope))
        self.set_active(False)

    def set_active(self, active):
        self._active = bool(active)
        if self._active:
            self._rest_button_color = (0.18, 0.48, 0.88, 0.96)
            self._pressed_button_color = (0.14, 0.39, 0.74, 0.98)
            self._border_color.rgba = COLORS["accent"]
            self._border_line.width = 1.8
            self.color = COLORS["text"]
        else:
            self._rest_button_color = (0.10, 0.16, 0.27, 0.92)
            self._pressed_button_color = (0.13, 0.22, 0.37, 0.96)
            self._border_color.rgba = COLORS["outline"]
            self._border_line.width = 1.2
            self.color = COLORS["text_soft"]
        self._button_color.rgba = self._rest_button_color


class RoomChoiceChip(AppButton):
    def __init__(self, text, value, on_select, **kwargs):
        size_hint = kwargs.pop("size_hint", (1, None))
        chip_width = kwargs.pop("width", dp(92))
        chip_height = kwargs.pop("height", dp(42))
        chip_font_size = kwargs.pop("font_size", sp(12.5))
        super().__init__(
            text=text,
            compact=True,
            font_size=chip_font_size,
            size_hint=size_hint,
            width=chip_width,
            height=chip_height,
            button_color=(0.10, 0.16, 0.27, 0.92),
            pressed_color=(0.13, 0.22, 0.37, 0.96),
            **kwargs,
        )
        self.value = str(value)
        self._on_select = on_select
        self._active = False
        self.max_lines = 1
        self.shorten = True
        self.shorten_from = "center"
        self.bind(on_release=lambda *_: self._on_select(self.value))
        self.set_active(False)

    def _sync_text(self, *_):
        self.text_size = (max(0, self.width - dp(18)), max(0, self.height - dp(12)))

    def set_active(self, active):
        self._active = bool(active)
        if self._active:
            self._rest_button_color = (0.18, 0.48, 0.88, 0.98)
            self._pressed_button_color = (0.15, 0.40, 0.76, 1.0)
            self._border_color.rgba = COLORS["accent"]
            self._border_line.width = 1.8
            self.color = COLORS["text"]
        else:
            self._rest_button_color = (0.10, 0.16, 0.27, 0.96)
            self._pressed_button_color = (0.13, 0.22, 0.37, 0.98)
            self._border_color.rgba = COLORS["outline_soft"] if "outline_soft" in COLORS else COLORS["outline"]
            self._border_line.width = 1.0
            self.color = COLORS["text"]
        self._button_color.rgba = self._rest_button_color


class CreateRoomScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        register_game_font()
        self.pending_room_config = None
        self._autofill_bots_on_next_create = 0
        self.visibility_scope = "public"
        self.private_room_code = ""
        self.players_value = "6"
        self.difficulty_value = "Средние"
        self.timer_value = "60 сек"
        self.player_choice_chips = []
        self.difficulty_choice_chips = []
        self.timer_choice_chips = []
        self._room_access_event = None
        self.room_access_popup = None
        self.room_access_popup_message_label = None
        self._create_in_progress = False
        self._create_request_token = 0
        self._code_preview_token = 0
        self._code_preview_in_progress = False
        self._window = Window

        root = ScreenBackground()
        scroll, content = build_scrollable_content(padding=[dp(18), dp(18), dp(18), dp(20)], spacing=12)
        self._content_layout = content

        top_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(52))
        back_btn = AppButton(text="Назад", compact=True, size_hint=(None, None), size=(dp(132), dp(48)))
        back_btn.bind(on_release=lambda *_: setattr(self.manager, "current", "start"))
        top_row.add_widget(back_btn)
        top_row.add_widget(Widget())
        content.add_widget(top_row)

        self.brand_title = BrandTitle(text="ALIAS ONLINE", height=dp(120), font_size=sp(42), shadow_step=dp(3))
        content.add_widget(self.brand_title)

        intro_card = RoundedPanel(
            orientation="vertical",
            padding=[dp(18), dp(16), dp(18), dp(16)],
            spacing=dp(8),
            size_hint_y=None,
            bg_color=COLORS["surface_card"],
        )
        self.intro_card = intro_card
        intro_card.bind(minimum_height=intro_card.setter("height"))
        intro_card._border_color.rgba = (1, 1, 1, 0.14)
        intro_card._border_line.width = 1.2
        intro_card.add_widget(PixelLabel(text="Новая комната", font_size=sp(22), center=True, size_hint_y=None))
        intro_card.add_widget(
            BodyLabel(
                center=True,
                color=COLORS["text_muted"],
                font_size=sp(12),
                text="Настрой комнату, выбери режим и сразу пригласи друзей в игру.",
                size_hint_y=None,
            )
        )
        self.balance_note = BodyLabel(
            center=True,
            color=COLORS["accent"],
            font_size=sp(12),
            text=f"Создание комнаты стоит {ROOM_CREATION_COST} AC.",
            size_hint_y=None,
        )
        intro_card.add_widget(self.balance_note)
        content.add_widget(intro_card)

        form_card = RoundedPanel(
            orientation="vertical",
            padding=[dp(20), dp(18), dp(20), dp(18)],
            spacing=dp(14),
            size_hint_y=None,
            bg_color=COLORS["surface_card"],
        )
        self.form_card = form_card
        form_card.bind(minimum_height=form_card.setter("height"))
        form_card._border_color.rgba = COLORS["outline_soft"] if "outline_soft" in COLORS else COLORS["outline"]
        form_card._border_line.width = 1.0
        form_card.add_widget(PixelLabel(text="Параметры комнаты", font_size=sp(15), center=True, size_hint_y=None))

        form_card.add_widget(BodyLabel(text="Название комнаты"))
        self.room_name_input = AppTextInput(hint_text="Например, Вечерний Alias", height=dp(48))
        form_card.add_widget(self.room_name_input)

        form_card.add_widget(BodyLabel(text="Сколько человек играет"))
        self.players_grid = GridLayout(
            cols=3,
            spacing=[dp(14), dp(10)],
            padding=[dp(8), dp(2), dp(8), dp(6)],
            size_hint_y=None,
            row_default_height=dp(48),
            row_force_default=True,
            col_default_width=dp(96),
            col_force_default=True,
        )
        self.players_grid._preferred_cols = 3
        self.players_grid._compact_cols = 2
        self.players_grid._compact_breakpoint = dp(330)
        self.players_grid._minimum_chip_width = dp(76)
        self.players_grid.bind(minimum_height=self.players_grid.setter("height"))
        for number in range(2, 13):
            chip = RoomChoiceChip(str(number), str(number), self._select_players, height=dp(46))
            self.player_choice_chips.append(chip)
            self.players_grid.add_widget(chip)
        self.players_grid.bind(width=lambda *_args, grid=self.players_grid: self._sync_choice_grid_width(grid, min_width=dp(92)))
        form_card.add_widget(self.players_grid)

        form_card.add_widget(BodyLabel(text="Сложность слов"))
        self.difficulty_grid = GridLayout(
            cols=4,
            spacing=[dp(12), dp(10)],
            padding=[dp(8), dp(2), dp(8), dp(4)],
            size_hint_y=None,
            row_default_height=dp(46),
            row_force_default=True,
            col_default_width=dp(108),
            col_force_default=True,
        )
        self.difficulty_grid._preferred_cols = 4
        self.difficulty_grid._compact_cols = 4
        self.difficulty_grid._compact_breakpoint = 0
        self.difficulty_grid._minimum_chip_width = dp(72)
        self.difficulty_grid.bind(minimum_height=self.difficulty_grid.setter("height"))
        for value in ["Легкие", "Средние", "Сложные", "Микс"]:
            chip = RoomChoiceChip(value, value, self._select_difficulty, height=dp(44), font_size=sp(12.4))
            self.difficulty_choice_chips.append(chip)
            self.difficulty_grid.add_widget(chip)
        self.difficulty_grid.bind(width=lambda *_args, grid=self.difficulty_grid: self._sync_choice_grid_width(grid, min_width=dp(72)))
        form_card.add_widget(self.difficulty_grid)

        form_card.add_widget(BodyLabel(text="Тип комнаты"))
        type_row = BoxLayout(orientation="horizontal", spacing=dp(10), size_hint_y=None, height=dp(46))
        self.public_chip = RoomTypeChip("Публичная", "public", self._select_visibility)
        self.private_chip = RoomTypeChip("Закрытая", "private", self._select_visibility)
        type_row.add_widget(self.public_chip)
        type_row.add_widget(self.private_chip)
        form_card.add_widget(type_row)

        self.type_hint_label = BodyLabel(
            color=COLORS["text_muted"],
            font_size=sp(11),
            text="Публичная комната будет видна в общем списке. Закрытая — только по коду.",
            size_hint_y=None,
        )
        form_card.add_widget(self.type_hint_label)

        form_card.add_widget(BodyLabel(text="Таймер раунда"))
        self.timer_grid = GridLayout(
            cols=2,
            spacing=[dp(16), dp(12)],
            padding=[dp(8), dp(2), dp(8), dp(8)],
            size_hint_y=None,
            row_default_height=dp(50),
            row_force_default=True,
            col_default_width=dp(116),
            col_force_default=True,
        )
        self.timer_grid._preferred_cols = 2
        self.timer_grid._compact_cols = 2
        self.timer_grid._compact_breakpoint = 0
        self.timer_grid._minimum_chip_width = dp(112)
        self.timer_grid.bind(minimum_height=self.timer_grid.setter("height"))
        for value in ["30 сек", "45 сек", "60 сек", "75 сек", "90 сек", "120 сек"]:
            chip = RoomChoiceChip(value, value, self._select_timer, height=dp(46), font_size=sp(12.3))
            self.timer_choice_chips.append(chip)
            self.timer_grid.add_widget(chip)
        self.timer_grid.bind(width=lambda *_args, grid=self.timer_grid: self._sync_choice_grid_width(grid, min_width=dp(112)))
        form_card.add_widget(self.timer_grid)
        content.add_widget(form_card)

        self.code_card_height = dp(0)
        self.code_card_host = BoxLayout(
            orientation="vertical",
            padding=[dp(0), dp(0), dp(0), dp(0)],
            size_hint_y=None,
            height=dp(0),
            opacity=0,
            disabled=True,
        )
        self.code_card = RoundedPanel(
            orientation="vertical",
            padding=[dp(18), dp(16), dp(18), dp(16)],
            spacing=dp(10),
            size_hint_y=None,
            height=dp(0),
            opacity=0,
            disabled=True,
            bg_color=(0.08, 0.14, 0.24, 0.92),
        )
        self.code_card.bind(minimum_height=self._sync_code_card_height)
        self.code_card.add_widget(PixelLabel(text="Код комнаты", font_size=sp(15), center=True, size_hint_y=None, height=dp(24)))
        self.code_card.add_widget(
            BodyLabel(
                center=True,
                color=COLORS["text_muted"],
                font_size=sp(11),
                text="Этот код можно отправить друзьям, чтобы они вошли именно в твою комнату.",
                size_hint_y=None,
                height=dp(52),
            )
        )

        code_value_wrap = RoundedPanel(
            orientation="vertical",
            size_hint_y=None,
            height=dp(74),
            padding=[dp(12), dp(12), dp(12), dp(12)],
            bg_color=(0.05, 0.09, 0.15, 0.96),
            shadow_alpha=0.14,
        )
        self.private_code_label = PixelLabel(text="------", font_size=sp(28), center=True, size_hint_y=None)
        code_value_wrap.add_widget(self.private_code_label)
        self.code_card.add_widget(code_value_wrap)

        copy_row = BoxLayout(orientation="horizontal", spacing=dp(10), size_hint_y=None, height=dp(44))
        copy_row.add_widget(Widget())
        self.copy_code_btn = AppButton(text="Скопировать код", compact=True, font_size=sp(14), size_hint=(None, None), size=(dp(210), dp(42)))
        self.copy_code_btn.bind(on_release=self._copy_private_code)
        copy_row.add_widget(self.copy_code_btn)
        copy_row.add_widget(Widget())
        self.code_card.add_widget(copy_row)
        content.add_widget(self.code_card_host)

        actions_card = RoundedPanel(
            orientation="vertical",
            padding=[dp(18), dp(16), dp(18), dp(16)],
            spacing=dp(10),
            size_hint_y=None,
            bg_color=COLORS["surface_card"],
        )
        self.actions_card = actions_card
        actions_card.bind(minimum_height=actions_card.setter("height"))
        actions_card._border_color.rgba = (1, 1, 1, 0.14)
        actions_card._border_line.width = 1.2
        create_row = BoxLayout(
            orientation="horizontal",
            spacing=dp(12),
            padding=[dp(4), 0, dp(4), 0],
            size_hint_y=None,
            height=dp(62),
        )
        self.create_row = create_row
        self.create_btn = AppButton(text="Создать комнату", font_size=sp(18))
        self.create_btn.size_hint_y = 1
        self.create_btn.bind(on_release=self.prepare_room)
        create_row.add_widget(self.create_btn)
        cost_chip = RoundedPanel(
            orientation="vertical",
            size_hint=(None, 1),
            width=dp(102),
            padding=[dp(8), dp(8), dp(8), dp(8)],
            bg_color=(0.11, 0.18, 0.30, 0.92),
            shadow_alpha=0.16,
        )
        self.cost_chip = cost_chip
        cost_chip.add_widget(
            PixelLabel(
                text=f"-{ROOM_CREATION_COST} AC",
                font_size=sp(13.4),
                center=True,
                size_hint_y=None,
                height=dp(24),
            )
        )
        create_row.add_widget(cost_chip)
        actions_card.add_widget(create_row)
        self.status_label = BodyLabel(
            center=True,
            color=COLORS["text_muted"],
            text="Выбери параметры комнаты и мы подготовим красивое онлайн-лобби.",
            size_hint_y=None,
        )
        actions_card.add_widget(self.status_label)
        content.add_widget(actions_card)

        root.add_widget(scroll)
        self.coin_badge = CoinBadge(pos_hint={"right": 0.965, "top": 0.96})
        root.add_widget(self.coin_badge)
        self.loading_overlay = LoadingOverlay()
        root.add_widget(self.loading_overlay)
        self.add_widget(root)

        self._select_visibility("public")
        self._select_players(self.players_value)
        self._select_difficulty(self.difficulty_value)
        self._select_timer(self.timer_value)
        Clock.schedule_once(lambda *_: self._sync_choice_grid_width(self.players_grid, min_width=dp(92)), 0)
        Clock.schedule_once(lambda *_: self._sync_choice_grid_width(self.difficulty_grid, min_width=dp(72)), 0)
        Clock.schedule_once(lambda *_: self._sync_choice_grid_width(self.timer_grid, min_width=dp(112)), 0)
        self.bind(size=self._schedule_responsive_layout)
        if self._window is not None:
            self._window.bind(size=self._schedule_responsive_layout)
        Clock.schedule_once(self._apply_responsive_layout, 0)

    def _room_access_message(self, remaining_seconds):
        app = App.get_running_app()
        if app is not None and hasattr(app, "format_room_access_message"):
            return app.format_room_access_message("Создание комнаты")
        minutes = max(1, (int(remaining_seconds) + 59) // 60)
        return f"Создание комнаты сейчас недоступно. Подожди примерно {minutes} мин."

    def on_pre_enter(self, *_):
        self._schedule_responsive_layout()
        self._start_room_access_watch()
        self._refresh_room_access_ui()
        app = App.get_running_app()
        if app is not None and hasattr(app, "_start_room_server_in_background"):
            app._start_room_server_in_background()
        player_name = app.resolve_player_name() if app is not None else None
        profile = app.current_profile() if app is not None else None
        if profile is None and app is not None and getattr(app, "guest_mode", False):
            profile = SimpleNamespace(email=None, alias_coins=self._resolve_coin_balance(app, None))
        room_access_state = app.room_access_state() if app is not None and hasattr(app, "room_access_state") else {"active": False}
        self.coin_badge.refresh_from_session()

        if room_access_state.get("active"):
            self.balance_note.color = COLORS["warning"]
            self.balance_note.text = self._room_access_message(room_access_state.get("remaining_seconds", 0))
            return

        if not player_name:
            self.balance_note.color = COLORS["warning"]
            self.balance_note.text = "Сначала начни сессию через вход, регистрацию или гостевой режим."
            self.create_btn.disabled = True
            return

        if profile is None:
            self.balance_note.color = COLORS["warning"]
            self.balance_note.text = "Не удалось определить баланс сессии. Перезапусти вход или гостевой режим."
            self.create_btn.disabled = True
            return

        self.create_btn.disabled = False
        self.balance_note.color = COLORS["accent"]
        self.balance_note.text = f"Баланс: {profile.alias_coins} AC. Создание комнаты стоит {ROOM_CREATION_COST} AC."
        if self.visibility_scope == "private":
            self._ensure_private_code_preview(force=not bool(self.private_room_code))

    def on_leave(self, *_):
        self._stop_room_access_watch()
        self._dismiss_room_access_popup()
        self._create_in_progress = False
        self._create_request_token += 1
        self._code_preview_token += 1
        self._code_preview_in_progress = False
        self.create_btn.disabled = False
        self.loading_overlay.hide()

    def _start_room_access_watch(self):
        self._stop_room_access_watch()
        self._room_access_event = Clock.schedule_interval(lambda _dt: self._tick_room_access_state(), 1.0)

    def _stop_room_access_watch(self):
        if self._room_access_event is not None:
            self._room_access_event.cancel()
            self._room_access_event = None

    def _tick_room_access_state(self):
        app = App.get_running_app()
        state = app.room_access_state() if app is not None and hasattr(app, "room_access_state") else {"active": False}
        locked = bool(state.get("active"))
        self._set_create_button_locked(locked)
        self._update_room_access_popup_message(state)
        if locked:
            self.balance_note.color = COLORS["warning"]
            self.balance_note.text = self._room_access_message(state.get("remaining_seconds", 0))
        else:
            profile = app.current_profile() if app is not None else None
            if profile is not None:
                self.balance_note.color = COLORS["accent"]
                self.balance_note.text = f"Баланс: {profile.alias_coins} AC. Создание комнаты стоит {ROOM_CREATION_COST} AC."
                self.coin_badge.set_value(profile.alias_coins)
            elif app is not None and getattr(app, "guest_mode", False):
                guest_coins = self._resolve_coin_balance(app, None)
                self.balance_note.color = COLORS["text_soft"]
                self.balance_note.text = f"Гостевой режим: {guest_coins} AC. Создание комнаты стоит {ROOM_CREATION_COST} AC."
                self.coin_badge.set_value(guest_coins)

    def _update_room_access_popup_message(self, state=None):
        if self.room_access_popup is None or self.room_access_popup_message_label is None:
            return

        app = App.get_running_app()
        if state is None:
            state = app.room_access_state() if app is not None and hasattr(app, "room_access_state") else {"active": False}

        if not bool(state.get("active")):
            self._dismiss_room_access_popup()
            return

        self.room_access_popup_message_label.text = self._room_access_message(state.get("remaining_seconds", 0))

    def _refresh_room_access_ui(self):
        app = App.get_running_app()
        state = app.room_access_state() if app is not None and hasattr(app, "room_access_state") else {"active": False}
        self._set_create_button_locked(bool(state.get("active")))

    def _set_create_button_locked(self, locked):
        if locked:
            self.create_btn._rest_button_color = COLORS["danger_button"]
            self.create_btn._pressed_button_color = COLORS["danger_button_pressed"]
            self.create_btn._border_color.rgba = (1, 0.82, 0.82, 0.30)
            self.create_btn.disabled = False
        else:
            self.create_btn._rest_button_color = COLORS["button"]
            self.create_btn._pressed_button_color = COLORS["button_pressed"]
            self.create_btn._border_color.rgba = COLORS["outline"]
        self.create_btn._button_color.rgba = self.create_btn._rest_button_color

    def _open_room_access_popup(self):
        self._dismiss_room_access_popup()

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
        panel.add_widget(PixelLabel(text="Создание временно закрыто", font_size=sp(18), center=True, size_hint_y=None))

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
            text=self._room_access_message(0),
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

    def _dismiss_room_access_popup(self):
        if self.room_access_popup is not None:
            popup = self.room_access_popup
            self.room_access_popup = None
            self.room_access_popup_message_label = None
            popup.dismiss()

    def _timer_to_seconds(self, timer_value):
        return int((timer_value or "").split()[0])

    def _resolve_coin_balance(self, app, profile):
        if profile is not None:
            try:
                return int(getattr(profile, "alias_coins", 0) or 0)
            except (TypeError, ValueError):
                return 0
        if app is not None and hasattr(app, "current_alias_coins"):
            try:
                return int(app.current_alias_coins() or 0)
            except (TypeError, ValueError):
                return 0
        return 0

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

        if self._content_layout is not None:
            side_pad = dp(16 if compact else 20)
            self._content_layout.padding = [side_pad, dp(14 if compact else 18), side_pad, dp(20 if compact else 24)]
            self._content_layout.spacing = dp(10 if compact else 12)

        if self.intro_card is not None:
            self.intro_card.padding = [dp(14 if compact else 18), dp(12 if compact else 16), dp(14 if compact else 18), dp(12 if compact else 16)]

        if self.form_card is not None:
            self.form_card.padding = [dp(14 if compact else 20), dp(14 if compact else 18), dp(14 if compact else 20), dp(14 if compact else 18)]
            self.form_card.spacing = dp(12 if compact else 14)

        if self.players_grid is not None:
            self.players_grid.spacing = [dp(12 if compact else 14), dp(10 if compact else 12)]
            self.players_grid.padding = [dp(8), dp(4), dp(8), dp(6)]
            self.players_grid.row_default_height = dp(46 if compact else 48)
        if self.difficulty_grid is not None:
            self.difficulty_grid.spacing = [dp(10 if compact else 12), dp(10 if compact else 12)]
            self.difficulty_grid.padding = [dp(8), dp(4), dp(8), dp(6)]
            self.difficulty_grid.row_default_height = dp(44 if compact else 46)
        if self.timer_grid is not None:
            self.timer_grid.spacing = [dp(18 if compact else 22), dp(12 if compact else 14)]
            self.timer_grid.padding = [dp(8), dp(4), dp(8), dp(8)]
            self.timer_grid.row_default_height = dp(48 if compact else 50)

        if self.actions_card is not None:
            self.actions_card.padding = [dp(14 if compact else 18), dp(14 if compact else 16), dp(14 if compact else 18), dp(14 if compact else 16)]
            self.actions_card.spacing = dp(9 if compact else 10)
        if self.create_row is not None:
            self.create_row.height = dp(60 if compact else 62)
            self.create_row.spacing = dp(12 if compact else 14)
            self.create_row.padding = [dp(2 if compact else 4), 0, dp(2 if compact else 4), 0]
        if self.cost_chip is not None:
            self.cost_chip.width = dp(98 if compact else 102)

        self._sync_choice_grid_width(self.players_grid, min_width=dp(92))
        self._sync_choice_grid_width(self.difficulty_grid, min_width=dp(72))
        self._sync_choice_grid_width(self.timer_grid, min_width=dp(112))
        if self.visibility_scope == "private":
            self._sync_code_card_height()

    def _sync_choice_grid_width(self, grid, min_width):
        if grid is None:
            return

        spacing = grid.spacing[0] if isinstance(grid.spacing, (list, tuple)) else grid.spacing
        padding = grid.padding if isinstance(grid.padding, (list, tuple)) else [grid.padding] * 4
        left_padding = padding[0] if len(padding) > 0 else 0
        right_padding = padding[2] if len(padding) > 2 else left_padding
        usable_width = max(0.0, float(grid.width - left_padding - right_padding))
        if usable_width <= 0:
            return

        preferred_cols = max(1, int(getattr(grid, "_preferred_cols", grid.cols or 1)))
        compact_cols = max(1, int(getattr(grid, "_compact_cols", preferred_cols)))
        compact_breakpoint = float(getattr(grid, "_compact_breakpoint", 0.0) or 0.0)
        target_cols = compact_cols if compact_breakpoint and usable_width < compact_breakpoint else preferred_cols
        max_cols = max(1, min(target_cols, len(getattr(grid, "children", [])) or target_cols))
        minimum_chip_width = float(getattr(grid, "_minimum_chip_width", min_width))

        while max_cols > 1:
            needed = max_cols * minimum_chip_width + max(0, max_cols - 1) * float(spacing)
            if needed <= usable_width + 0.5:
                break
            max_cols -= 1

        grid.cols = max(1, max_cols)
        available_width = max(dp(60), usable_width - float(spacing) * max(0, grid.cols - 1))
        column_width = max(dp(60), available_width / max(1, int(grid.cols or 1)))
        grid.col_default_width = column_width

    def _local_code_fallback(self):
        alphabet = string.ascii_uppercase + string.digits
        return "".join(random.choice(alphabet) for _ in range(6))

    def _sync_code_card_height(self, *_):
        if self.code_card is None or self.code_card_host is None:
            return
        if self.code_card.parent is not self.code_card_host or self.code_card.disabled:
            return

        target_height = max(dp(190), float(self.code_card.minimum_height or 0))
        self.code_card_height = target_height
        if abs(float(self.code_card.height) - target_height) > 0.5:
            self.code_card.height = target_height
        if abs(float(self.code_card_host.height) - target_height) > 0.5:
            self.code_card_host.height = target_height

    def _set_code_card_visibility(self, visible):
        is_visible = bool(visible)
        self.code_card.disabled = not is_visible
        self.code_card.opacity = 1 if is_visible else 0
        self.code_card_host.disabled = not is_visible
        self.code_card_host.opacity = 1 if is_visible else 0

        if is_visible:
            if self.code_card.parent is not self.code_card_host:
                if self.code_card.parent is not None:
                    self.code_card.parent.remove_widget(self.code_card)
                self.code_card_host.add_widget(self.code_card)
            self._sync_code_card_height()
            Clock.schedule_once(self._sync_code_card_height, 0)
            Clock.schedule_once(self._sync_code_card_height, 0.05)
        else:
            self.code_card.height = dp(0)
            self.code_card_host.height = dp(0)
            if self.code_card.parent is self.code_card_host:
                self.code_card_host.remove_widget(self.code_card)

    def _select_visibility(self, scope):
        self.visibility_scope = "private" if scope == "private" else "public"
        self.public_chip.set_active(self.visibility_scope == "public")
        self.private_chip.set_active(self.visibility_scope == "private")
        self._set_code_card_visibility(self.visibility_scope == "private")
        Clock.schedule_once(lambda *_: self._sync_choice_grid_width(self.players_grid, min_width=dp(92)), 0)
        Clock.schedule_once(lambda *_: self._sync_choice_grid_width(self.difficulty_grid, min_width=dp(72)), 0)
        Clock.schedule_once(lambda *_: self._sync_choice_grid_width(self.timer_grid, min_width=dp(112)), 0)
        if self.visibility_scope == "private":
            self.type_hint_label.text = "Закрытая комната не попадет в список. Друзья смогут войти по коду ниже."
            self._ensure_private_code_preview(force=not bool(self.private_room_code))
        else:
            self.type_hint_label.text = "Публичная комната будет видна в общем списке. Закрытая — только по коду."

    def _select_players(self, value):
        self.players_value = str(value)
        for chip in self.player_choice_chips:
            chip.set_active(chip.value == self.players_value)

    def _select_difficulty(self, value):
        self.difficulty_value = str(value)
        for chip in self.difficulty_choice_chips:
            chip.set_active(chip.value == self.difficulty_value)

    def _select_timer(self, value):
        self.timer_value = str(value)
        for chip in self.timer_choice_chips:
            chip.set_active(chip.value == self.timer_value)

    def _ensure_private_code_preview(self, force=False):
        if self.visibility_scope != "private":
            return
        if self.private_room_code and not force:
            self.private_code_label.text = self.private_room_code
        else:
            self.private_room_code = self._local_code_fallback()
        self.private_code_label.text = self.private_room_code
        self._request_private_code_preview()

    def _request_private_code_preview(self):
        if self.visibility_scope != "private":
            return
        if self._code_preview_in_progress:
            return

        self._code_preview_in_progress = True
        self._code_preview_token += 1
        request_token = self._code_preview_token
        worker = Thread(target=self._load_private_code_worker, args=(request_token,), daemon=True)
        worker.start()

    def _load_private_code_worker(self, request_token):
        code_value = ""
        try:
            code_value = (generate_room_code_preview() or "").strip().upper()
        except (ConnectionError, ValueError):
            code_value = ""
        Clock.schedule_once(
            lambda _dt, token=request_token, code=code_value: self._finish_private_code_preview(token, code)
        )

    def _finish_private_code_preview(self, request_token, code_value):
        if request_token != self._code_preview_token:
            return

        self._code_preview_in_progress = False
        if self.visibility_scope != "private":
            return

        if code_value:
            self.private_room_code = code_value
            self.private_code_label.text = code_value

    def _copy_private_code(self, *_):
        if not self.private_room_code:
            self._ensure_private_code_preview(force=True)
        Clipboard.copy(self.private_room_code or "")
        self.status_label.color = COLORS["accent"]
        self.status_label.text = f"Код {self.private_room_code} скопирован. Теперь его можно отправить друзьям."

    def _spawn_test_bots(self, room_code, max_players):
        return 0, None

    def prepare_room(self, *_):
        if self._create_in_progress:
            return
        app = App.get_running_app()
        if app is not None and hasattr(app, "_start_room_server_in_background"):
            app._start_room_server_in_background()
        player_name = app.resolve_player_name() if app is not None else None
        profile = app.current_profile() if app is not None else None
        if profile is None and app is not None and getattr(app, "guest_mode", False):
            profile = SimpleNamespace(email=None, alias_coins=self._resolve_coin_balance(app, None))
        room_access_state = app.room_access_state() if app is not None and hasattr(app, "room_access_state") else {"active": False}
        room_name = self.room_name_input.text.strip()
        players = self.players_value
        difficulty = self.difficulty_value
        round_timer = self.timer_value

        if room_access_state.get("active"):
            self.status_label.color = COLORS["warning"]
            self.status_label.text = self._room_access_message(room_access_state.get("remaining_seconds", 0))
            self._open_room_access_popup()
            return

        if not player_name:
            self.status_label.color = COLORS["error"]
            self.status_label.text = "Сначала начни сессию через вход, регистрацию или гостевой режим."
            return

        if profile is None:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Не удалось определить баланс сессии. Перезапусти вход или гостевой режим."
            return

        if int(getattr(profile, "alias_coins", 0) or 0) < ROOM_CREATION_COST:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = f"Недостаточно AC. Нужно {ROOM_CREATION_COST}, а у тебя сейчас {profile.alias_coins}."
            return

        if not room_name:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Добавь название комнаты."
            return

        if len(room_name) < 3:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Название комнаты должно быть не короче 3 символов."
            return

        if not players:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Выбери количество игроков."
            return

        if not difficulty:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Выбери сложность слов."
            return

        if not round_timer:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Выбери таймер раунда."
            return

        requested_players = int(players)

        requested_code = None
        visibility_label = "Публичная" if self.visibility_scope == "public" else "Закрытая"
        if self.visibility_scope == "private":
            self._ensure_private_code_preview(force=not bool(self.private_room_code))
            requested_code = self.private_room_code

        self._start_create_room_request(
            player_name=player_name,
            profile=profile,
            room_name=room_name,
            requested_players=requested_players,
            difficulty=difficulty,
            visibility_label=visibility_label,
            requested_code=requested_code,
            round_timer=round_timer,
        )
        return

    def _start_create_room_request(
        self,
        *,
        player_name,
        profile,
        room_name,
        requested_players,
        difficulty,
        visibility_label,
        requested_code,
        round_timer,
    ):
        self._create_in_progress = True
        self._create_request_token += 1
        request_token = self._create_request_token
        self.create_btn.disabled = True
        app = App.get_running_app()
        client_id = app.resolve_client_id() if app is not None and hasattr(app, "resolve_client_id") else ""
        self.loading_overlay.show("Создаем комнату...")

        payload = {
            "player_name": player_name,
            "room_name": room_name,
            "requested_players": int(requested_players),
            "difficulty": difficulty,
            "visibility_label": visibility_label,
            "visibility_scope": self.visibility_scope,
            "round_timer_sec": self._timer_to_seconds(round_timer),
            "requested_code": requested_code,
            "profile_email": getattr(profile, "email", None),
            "profile_fallback": profile,
            "is_guest": not bool(getattr(profile, "email", None)),
            "client_id": client_id,
        }
        worker = Thread(target=self._create_room_worker_async, args=(request_token, payload), daemon=True)
        worker.start()

    def _create_room_worker_async(self, request_token, payload):
        result = {"status": "error", "message": "Не удалось создать комнату.", "tone": "error"}
        try:
            room = create_online_room(
                host_name=payload["player_name"],
                room_name=payload["room_name"],
                max_players=payload["requested_players"],
                difficulty=payload["difficulty"],
                visibility=payload["visibility_label"],
                visibility_scope=payload["visibility_scope"],
                round_timer_sec=payload["round_timer_sec"],
                client_id=payload.get("client_id"),
                requested_code=payload["requested_code"],
            )

            room_code = room.get("code")
            active_room = room
            if room_code:
                try:
                    active_room = join_online_room(
                        room_code=room_code,
                        player_name=payload["player_name"],
                        is_guest=bool(payload.get("is_guest")),
                        client_id=payload.get("client_id"),
                    )
                except (ConnectionError, ValueError):
                    active_room = room

            updated_profile = None
            if payload.get("profile_email"):
                try:
                    updated_profile = spend_alias_coins(email=payload["profile_email"], amount=ROOM_CREATION_COST)
                except ValueError:
                    updated_profile = payload["profile_fallback"]

            result = {
                "status": "success",
                "room": room,
                "active_room": active_room,
                "room_code": room_code,
                "joined_as": (active_room.get("_joined_as") or "").strip(),
                "updated_profile": updated_profile,
                "room_name": payload["room_name"],
                "is_guest": bool(payload.get("is_guest")),
            }
        except ConnectionError as error:
            result = {"status": "error", "message": str(error), "tone": "error"}
        except ValueError as error:
            result = {"status": "error", "message": str(error), "tone": "warning"}
        except Exception as error:
            result = {"status": "error", "message": f"Неожиданная ошибка: {error}", "tone": "error"}

        Clock.schedule_once(lambda _dt, token=request_token, data=result: self._finish_create_room_async(token, data))

    def _finish_create_room_async(self, request_token, result):
        if request_token != self._create_request_token:
            return

        self._create_in_progress = False
        self.create_btn.disabled = False
        self.loading_overlay.hide()

        if result.get("status") != "success":
            tone = result.get("tone", "error")
            self.status_label.color = COLORS["warning"] if tone == "warning" else COLORS["error"]
            self.status_label.text = result.get("message") or "Не удалось создать комнату."
            return

        room = result.get("room") or {}
        active_room = result.get("active_room") or room
        room_code = result.get("room_code")
        updated_profile = result.get("updated_profile")
        joined_as = (result.get("joined_as") or "").strip()
        is_guest = bool(result.get("is_guest"))
        app = App.get_running_app()
        if joined_as and app is not None and hasattr(app, "adopt_room_player_name"):
            app.adopt_room_player_name(joined_as)

        if self.visibility_scope == "private" and room_code:
            self.private_room_code = room_code
            self.private_code_label.text = room_code

        self.pending_room_config = active_room
        current_coins = "?"
        if updated_profile is not None:
            self.coin_badge.set_value(updated_profile.alias_coins)
            current_coins = updated_profile.alias_coins
        elif is_guest and app is not None and hasattr(app, "try_spend_guest_alias_coins"):
            spent_ok, remaining = app.try_spend_guest_alias_coins(ROOM_CREATION_COST)
            current_coins = remaining
            self.coin_badge.set_value(remaining)
            if not spent_ok:
                self.status_label.color = COLORS["warning"]
                self.status_label.text = (
                    f"Комната создана (код {room_code or '----'}), но не удалось списать {ROOM_CREATION_COST} AC."
                )

        self.status_label.color = COLORS["success"]
        self.status_label.text = (
            f"Комната «{room.get('room_name', result.get('room_name', 'Комната'))}» готова. "
            f"Код: {room_code or '----'}. Осталось {current_coins} AC."
        )
        if app is not None:
            app.set_active_room(active_room)
            if hasattr(app, "ensure_screen"):
                app.ensure_screen("room")
        if self.manager is not None:
            self.manager.current = "room"
