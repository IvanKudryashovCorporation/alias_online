import random
import string

from kivy.app import App
from kivy.core.clipboard import Clipboard
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.screenmanager import Screen
from kivy.uix.spinner import Spinner, SpinnerOption
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


class RoomSpinnerOption(SpinnerOption):
    def __init__(self, **kwargs):
        register_game_font()
        super().__init__(**kwargs)
        self.font_name = "GameFont"
        self.font_size = sp(14)
        self.color = COLORS["text"]
        self.background_normal = ""
        self.background_color = COLORS["surface_strong"]
        self.size_hint_y = None
        self.height = dp(42)


class RoomSpinner(Spinner):
    def __init__(self, placeholder, values, **kwargs):
        register_game_font()
        super().__init__(
            text=placeholder,
            values=values,
            option_cls=RoomSpinnerOption,
            size_hint_y=None,
            height=dp(48),
            **kwargs,
        )
        self.placeholder = placeholder
        self.font_name = "GameFont"
        self.font_size = sp(14)
        self.background_normal = ""
        self.background_down = ""
        self.bind(text=self._sync_visual_state)
        self._sync_visual_state()

    def selected_value(self):
        return None if self.text == self.placeholder else self.text

    def _sync_visual_state(self, *_):
        selected = self.text != self.placeholder
        self.color = COLORS["input_text"] if selected else COLORS["text_muted"]
        self.background_color = (0.11, 0.18, 0.30, 0.98) if selected else COLORS["input_bg"]


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
        super().__init__(
            text=text,
            compact=True,
            font_size=sp(13),
            size_hint=(1, None),
            height=dp(42),
            button_color=(0.10, 0.16, 0.27, 0.92),
            pressed_color=(0.13, 0.22, 0.37, 0.96),
            **kwargs,
        )
        self.value = str(value)
        self._on_select = on_select
        self._active = False
        self.bind(on_release=lambda *_: self._on_select(self.value))
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
            self._border_color.rgba = COLORS["outline_soft"] if "outline_soft" in COLORS else COLORS["outline"]
            self._border_line.width = 1.0
            self.color = COLORS["text_soft"]
        self._button_color.rgba = self._rest_button_color


class CreateRoomScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        register_game_font()
        self.pending_room_config = None
        self._autofill_bots_on_next_create = 4
        self.visibility_scope = "public"
        self.private_room_code = ""
        self.rounds_value = "5"
        self.round_choice_chips = []

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
            padding=[dp(18), dp(16), dp(18), dp(16)],
            spacing=dp(10),
            size_hint_y=None,
        )
        form_card.bind(minimum_height=form_card.setter("height"))
        form_card.add_widget(PixelLabel(text="Параметры комнаты", font_size=sp(15), center=True, size_hint_y=None))

        form_card.add_widget(BodyLabel(text="Название комнаты"))
        self.room_name_input = AppTextInput(hint_text="Например, Вечерний Alias", height=dp(48))
        form_card.add_widget(self.room_name_input)

        form_card.add_widget(BodyLabel(text="Сколько человек играет"))
        self.players_spinner = RoomSpinner("Выбери число игроков", [str(number) for number in range(2, 13)])
        form_card.add_widget(self.players_spinner)

        form_card.add_widget(BodyLabel(text="Сложность слов"))
        self.difficulty_spinner = RoomSpinner(
            "Выбери сложность слов",
            ["Легкие", "Средние", "Сложные", "Микс"],
        )
        form_card.add_widget(self.difficulty_spinner)

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
        self.round_timer_spinner = RoomSpinner(
            "Выбери таймер",
            ["30 сек", "45 сек", "60 сек", "75 сек", "90 сек", "120 сек"],
        )
        form_card.add_widget(self.round_timer_spinner)

        form_card.add_widget(BodyLabel(text="Количество раундов"))
        self.rounds_grid = GridLayout(
            cols=4,
            spacing=dp(8),
            size_hint_y=None,
            row_default_height=dp(42),
            row_force_default=True,
        )
        self.rounds_grid.bind(minimum_height=self.rounds_grid.setter("height"))
        for number in range(3, 11):
            chip = RoomChoiceChip(str(number), str(number), self._select_rounds)
            self.round_choice_chips.append(chip)
            self.rounds_grid.add_widget(chip)
        form_card.add_widget(self.rounds_grid)
        form_card.add_widget(
            BodyLabel(
                color=COLORS["text_muted"],
                font_size=sp(11),
                text="Количество раундов выбирается сразу кнопками, поэтому значение не потеряется и всегда кликается.",
                size_hint_y=None,
            )
        )
        content.add_widget(form_card)

        self.code_card_height = dp(188)
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
        content.add_widget(self.code_card)

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
        self._select_rounds(self.rounds_value)

    def _room_access_message(self, remaining_seconds):
        minutes = max(1, (int(remaining_seconds) + 59) // 60)
        return f"После выхода из матча доступ к комнатам временно закрыт. Подожди примерно {minutes} мин."

    def on_pre_enter(self, *_):
        app = App.get_running_app()
        player_name = app.resolve_player_name() if app is not None else None
        profile = app.current_profile() if app is not None else None
        room_access_state = app.room_access_state() if app is not None and hasattr(app, "room_access_state") else {"active": False}
        self.coin_badge.refresh_from_session()

        if room_access_state.get("active"):
            self.balance_note.color = COLORS["warning"]
            self.balance_note.text = self._room_access_message(room_access_state.get("remaining_seconds", 0))
            self.create_btn.disabled = True
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

    def _timer_to_seconds(self, timer_value):
        return int((timer_value or "").split()[0])

    def _local_code_fallback(self):
        alphabet = string.ascii_uppercase + string.digits
        return "".join(random.choice(alphabet) for _ in range(6))

    def _set_code_card_visibility(self, visible):
        self.code_card.disabled = not visible
        self.code_card.opacity = 1 if visible else 0
        self.code_card.height = self.code_card_height if visible else dp(0)

    def _select_visibility(self, scope):
        self.visibility_scope = "private" if scope == "private" else "public"
        self.public_chip.set_active(self.visibility_scope == "public")
        self.private_chip.set_active(self.visibility_scope == "private")
        self._set_code_card_visibility(self.visibility_scope == "private")
        if self.visibility_scope == "private":
            self.type_hint_label.text = "Закрытая комната не попадет в список. Друзья смогут войти по коду ниже."
            self._ensure_private_code_preview(force=not bool(self.private_room_code))
        else:
            self.type_hint_label.text = "Публичная комната будет видна в общем списке. Закрытая — только по коду."

    def _select_rounds(self, value):
        self.rounds_value = str(value)
        for chip in self.round_choice_chips:
            chip.set_active(chip.value == self.rounds_value)

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
        players = self.players_spinner.selected_value()
        difficulty = self.difficulty_spinner.selected_value()
        round_timer = self.round_timer_spinner.selected_value()
        rounds = self.rounds_value

        if room_access_state.get("active"):
            self.status_label.color = COLORS["warning"]
            self.status_label.text = self._room_access_message(room_access_state.get("remaining_seconds", 0))
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

        if not rounds:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Выбери количество раундов."
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
                rounds=int(rounds),
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
