import random
import string

from kivy.app import App
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
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
        self._autofill_bots_on_next_create = 4
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

        root = ScreenBackground()
        scroll, content = build_scrollable_content(padding=[dp(20), dp(22), dp(20), dp(24)], spacing=12)

        top_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(52))
        back_btn = AppButton(text="Назад", compact=True, size_hint=(None, None), size=(dp(132), dp(48)))
        back_btn.bind(on_release=lambda *_: setattr(self.manager, "current", "start"))
        top_row.add_widget(back_btn)
        top_row.add_widget(Widget())
        content.add_widget(top_row)

        content.add_widget(BrandTitle(text="ALIAS ONLINE", height=dp(104), font_size=sp(38), shadow_step=dp(3)))

        intro_card = RoundedPanel(
            orientation="vertical",
            padding=[dp(18), dp(16), dp(18), dp(16)],
            spacing=dp(8),
            size_hint_y=None,
            bg_color=COLORS["surface_card"],
        )
        intro_card.bind(minimum_height=intro_card.setter("height"))
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
            padding=[dp(22), dp(18), dp(22), dp(18)],
            spacing=dp(14),
            size_hint_y=None,
        )
        form_card.bind(minimum_height=form_card.setter("height"))
        form_card.add_widget(PixelLabel(text="Параметры комнаты", font_size=sp(15), center=True, size_hint_y=None))

        form_card.add_widget(BodyLabel(text="Название комнаты"))
        self.room_name_input = AppTextInput(hint_text="Например, Вечерний Alias", height=dp(48))
        form_card.add_widget(self.room_name_input)

        form_card.add_widget(BodyLabel(text="Сколько человек играет"))
        self.players_grid = GridLayout(
            cols=3,
            spacing=[dp(12), dp(12)],
            padding=[dp(8), dp(2), dp(8), dp(6)],
            size_hint_y=None,
            row_default_height=dp(48),
            row_force_default=True,
            col_default_width=dp(94),
            col_force_default=True,
        )
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
            spacing=[dp(10), dp(0)],
            padding=[dp(8), dp(2), dp(8), dp(4)],
            size_hint_y=None,
            row_default_height=dp(46),
            row_force_default=True,
            col_default_width=dp(82),
            col_force_default=True,
        )
        self.difficulty_grid.bind(minimum_height=self.difficulty_grid.setter("height"))
        for value in ["Легкие", "Средние", "Сложные", "Микс"]:
            chip = RoomChoiceChip(value, value, self._select_difficulty, height=dp(44), font_size=sp(11.8))
            self.difficulty_choice_chips.append(chip)
            self.difficulty_grid.add_widget(chip)
        self.difficulty_grid.bind(width=lambda *_args, grid=self.difficulty_grid: self._sync_choice_grid_width(grid, min_width=dp(78)))
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
            cols=3,
            spacing=[dp(16), dp(16)],
            padding=[dp(8), dp(2), dp(8), dp(8)],
            size_hint_y=None,
            row_default_height=dp(50),
            row_force_default=True,
            col_default_width=dp(104),
            col_force_default=True,
        )
        self.timer_grid.bind(minimum_height=self.timer_grid.setter("height"))
        for value in ["30 сек", "45 сек", "60 сек", "75 сек", "90 сек", "120 сек"]:
            chip = RoomChoiceChip(value, value, self._select_timer, height=dp(46), font_size=sp(12.2))
            self.timer_choice_chips.append(chip)
            self.timer_grid.add_widget(chip)
        self.timer_grid.bind(width=lambda *_args, grid=self.timer_grid: self._sync_choice_grid_width(grid, min_width=dp(96)))
        form_card.add_widget(self.timer_grid)
        content.add_widget(form_card)

        self.code_card_height = dp(188)
        self.code_card_host = BoxLayout(
            orientation="vertical",
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
        self.code_card.add_widget(PixelLabel(text="Код комнаты", font_size=sp(15), center=True, size_hint_y=None))
        self.code_card.add_widget(
            BodyLabel(
                center=True,
                color=COLORS["text_muted"],
                font_size=sp(11),
                text="Этот код можно отправить друзьям, чтобы они вошли именно в твою комнату.",
                size_hint_y=None,
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
        )
        actions_card.bind(minimum_height=actions_card.setter("height"))
        self.create_btn = AppButton(text="Создать комнату", font_size=sp(18))
        self.create_btn.bind(on_release=self.prepare_room)
        actions_card.add_widget(self.create_btn)
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
        self.add_widget(root)

        self._select_visibility("public")
        self._select_players(self.players_value)
        self._select_difficulty(self.difficulty_value)
        self._select_timer(self.timer_value)
        Clock.schedule_once(lambda *_: self._sync_choice_grid_width(self.players_grid, min_width=dp(92)), 0)
        Clock.schedule_once(lambda *_: self._sync_choice_grid_width(self.difficulty_grid, min_width=dp(78)), 0)
        Clock.schedule_once(lambda *_: self._sync_choice_grid_width(self.timer_grid, min_width=dp(96)), 0)

    def _room_access_message(self, remaining_seconds):
        app = App.get_running_app()
        if app is not None and hasattr(app, "format_room_access_message"):
            return app.format_room_access_message("Создание комнаты")
        minutes = max(1, (int(remaining_seconds) + 59) // 60)
        return f"Создание комнаты сейчас недоступно. Подожди примерно {minutes} мин."

    def on_pre_enter(self, *_):
        self._start_room_access_watch()
        self._refresh_room_access_ui()
        app = App.get_running_app()
        player_name = app.resolve_player_name() if app is not None else None
        profile = app.current_profile() if app is not None else None
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
            self.balance_note.text = f"Гость может только присоединяться к комнатам. Для создания нужно {ROOM_CREATION_COST} AC."
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

    def _dismiss_room_access_popup(self):
        if self.room_access_popup is not None:
            popup = self.room_access_popup
            self.room_access_popup = None
            self.room_access_popup_message_label = None
            popup.dismiss()

    def _timer_to_seconds(self, timer_value):
        return int((timer_value or "").split()[0])

    def _sync_choice_grid_width(self, grid, min_width):
        if grid is None:
            return

        spacing = grid.spacing[0] if isinstance(grid.spacing, (list, tuple)) else grid.spacing
        padding = grid.padding if isinstance(grid.padding, (list, tuple)) else [grid.padding] * 4
        left_padding = padding[0] if len(padding) > 0 else 0
        right_padding = padding[2] if len(padding) > 2 else left_padding
        available_width = max(float(min_width), grid.width - left_padding - right_padding - spacing * max(0, grid.cols - 1))
        column_width = max(float(min_width), available_width / max(1, int(grid.cols or 1)))
        grid.col_default_width = column_width

    def _local_code_fallback(self):
        alphabet = string.ascii_uppercase + string.digits
        return "".join(random.choice(alphabet) for _ in range(6))

    def _set_code_card_visibility(self, visible):
        self.code_card.disabled = not visible
        self.code_card.opacity = 1 if visible else 0
        self.code_card.height = self.code_card_height if visible else dp(0)
        self.code_card_host.disabled = not visible
        self.code_card_host.opacity = 1 if visible else 0
        self.code_card_host.height = self.code_card_height if visible else dp(0)
        if visible:
            if self.code_card.parent is not self.code_card_host:
                if self.code_card.parent is not None:
                    self.code_card.parent.remove_widget(self.code_card)
                self.code_card_host.add_widget(self.code_card)
        elif self.code_card.parent is self.code_card_host:
            self.code_card_host.remove_widget(self.code_card)

    def _select_visibility(self, scope):
        self.visibility_scope = "private" if scope == "private" else "public"
        self.public_chip.set_active(self.visibility_scope == "public")
        self.private_chip.set_active(self.visibility_scope == "private")
        self._set_code_card_visibility(self.visibility_scope == "private")
        Clock.schedule_once(lambda *_: self._sync_choice_grid_width(self.players_grid, min_width=dp(92)), 0)
        Clock.schedule_once(lambda *_: self._sync_choice_grid_width(self.difficulty_grid, min_width=dp(78)), 0)
        Clock.schedule_once(lambda *_: self._sync_choice_grid_width(self.timer_grid, min_width=dp(96)), 0)
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
            return
        try:
            self.private_room_code = generate_room_code_preview() or self._local_code_fallback()
        except (ConnectionError, ValueError):
            self.private_room_code = self._local_code_fallback()
        self.private_code_label.text = self.private_room_code

    def _copy_private_code(self, *_):
        if not self.private_room_code:
            self._ensure_private_code_preview(force=True)
        Clipboard.copy(self.private_room_code or "")
        self.status_label.color = COLORS["accent"]
        self.status_label.text = f"Код {self.private_room_code} скопирован. Теперь его можно отправить друзьям."

    def _spawn_test_bots(self, room_code, max_players):
        bots_to_add = max(0, int(self._autofill_bots_on_next_create or 0))
        free_slots = max(0, int(max_players) - 1)
        target_count = min(bots_to_add, free_slots)
        latest_room = None
        spawned = 0

        for index in range(1, target_count + 1):
            bot_name = f"Bot {index}"
            try:
                latest_room = join_online_room(room_code=room_code, player_name=bot_name)
                spawned += 1
            except (ConnectionError, ValueError):
                break

        if spawned:
            self._autofill_bots_on_next_create = 0

        return spawned, latest_room

    def prepare_room(self, *_):
        app = App.get_running_app()
        player_name = app.resolve_player_name() if app is not None else None
        profile = app.current_profile() if app is not None else None
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
            self.status_label.text = f"Гостевой режим не может создавать комнаты. Для создания нужно {ROOM_CREATION_COST} AC."
            return

        if profile.alias_coins < ROOM_CREATION_COST:
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
        if self._autofill_bots_on_next_create:
            requested_players = max(requested_players, 1 + int(self._autofill_bots_on_next_create))

        requested_code = None
        visibility_label = "Публичная" if self.visibility_scope == "public" else "Закрытая"
        if self.visibility_scope == "private":
            self._ensure_private_code_preview(force=not bool(self.private_room_code))
            requested_code = self.private_room_code

        try:
            room = create_online_room(
                host_name=player_name,
                room_name=room_name,
                max_players=requested_players,
                difficulty=difficulty,
                visibility=visibility_label,
                visibility_scope=self.visibility_scope,
                round_timer_sec=self._timer_to_seconds(round_timer),
                requested_code=requested_code,
            )
        except ConnectionError as error:
            self.status_label.color = COLORS["error"]
            self.status_label.text = str(error)
            return
        except ValueError as error:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = str(error)
            return

        spawned_bots = 0
        latest_room = None
        room_code = room.get("code")
        if room_code:
            if self.visibility_scope == "private":
                self.private_room_code = room_code
                self.private_code_label.text = room_code
            spawned_bots, latest_room = self._spawn_test_bots(room_code, room.get("max_players", requested_players))

        active_room = latest_room or room
        if room_code:
            try:
                active_room = join_online_room(room_code=room_code, player_name=player_name)
            except (ConnectionError, ValueError):
                active_room = latest_room or room

        self.pending_room_config = active_room
        try:
            updated_profile = spend_alias_coins(email=profile.email, amount=ROOM_CREATION_COST)
        except ValueError:
            updated_profile = profile

        self.coin_badge.set_value(updated_profile.alias_coins)
        self.status_label.color = COLORS["success"]
        self.status_label.text = (
            f"Комната «{room.get('room_name', room_name)}» готова. "
            f"Код: {room_code or '----'}. "
            f"Осталось {updated_profile.alias_coins} AC. "
            f"Ботов подключено: {spawned_bots}."
        )
        if app is not None:
            app.set_active_room(active_room)
        self.manager.current = "room"
