from kivy.app import App
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen
from kivy.uix.spinner import Spinner, SpinnerOption

from services import ROOM_CREATION_COST, create_online_room, room_server_url, spend_alias_coins
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
        self.color = COLORS["input_text"]
        self.background_normal = ""
        self.background_down = ""
        self.background_color = COLORS["input_bg"]

    def selected_value(self):
        return None if self.text == self.placeholder else self.text


class CreateRoomScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        register_game_font()
        self.pending_room_config = None

        root = ScreenBackground()
        scroll, content = build_scrollable_content(padding=[dp(20), dp(24), dp(20), dp(20)], spacing=10)

        back_btn = AppButton(text="Назад", compact=True, size_hint_x=None, width=dp(132))
        back_btn.bind(on_release=lambda *_: setattr(self.manager, "current", "start"))
        content.add_widget(back_btn)
        content.add_widget(BrandTitle(text="ALIAS ONLINE", height=dp(116), font_size=sp(40), shadow_step=dp(3)))
        content.add_widget(PixelLabel(text="Создать комнату", font_size=sp(20), center=True))

        profile_card = RoundedPanel(
            orientation="vertical",
            padding=[dp(16), dp(14), dp(16), dp(14)],
            spacing=dp(8),
            size_hint_y=None,
        )
        profile_card.bind(minimum_height=profile_card.setter("height"))
        profile_card.add_widget(BodyLabel(text="Хост комнаты"))
        self.profile_name_label = BodyLabel(
            color=COLORS["accent"],
            text="Имя подтянется из текущего профиля или гостевого входа.",
        )
        profile_card.add_widget(self.profile_name_label)
        self.coin_balance_label = BodyLabel(
            color=COLORS["text_muted"],
            font_size=sp(11),
            text=f"Создание комнаты стоит {ROOM_CREATION_COST} Alias Coin.",
        )
        profile_card.add_widget(self.coin_balance_label)
        self.server_label = BodyLabel(
            color=COLORS["text_muted"],
            font_size=sp(11),
            text=f"Сервер комнат: {room_server_url()}",
        )
        profile_card.add_widget(self.server_label)
        content.add_widget(profile_card)

        form_card = RoundedPanel(
            orientation="vertical",
            padding=[dp(16), dp(14), dp(16), dp(14)],
            spacing=dp(8),
            size_hint_y=None,
        )
        form_card.bind(minimum_height=form_card.setter("height"))
        form_card.add_widget(PixelLabel(text="Параметры комнаты", font_size=sp(13), center=True))

        form_card.add_widget(BodyLabel(text="Название комнаты"))
        self.room_name_input = AppTextInput(hint_text="Например, Вечерний Alias", height=dp(48))
        form_card.add_widget(self.room_name_input)

        form_card.add_widget(BodyLabel(text="Сколько человек играет"))
        self.players_spinner = RoomSpinner(
            "Выбери число игроков",
            [str(number) for number in range(2, 13)],
        )
        form_card.add_widget(self.players_spinner)

        form_card.add_widget(BodyLabel(text="Сложность слов"))
        self.difficulty_spinner = RoomSpinner(
            "Выбери сложность слов",
            ["Легкие", "Средние", "Сложные", "Микс"],
        )
        form_card.add_widget(self.difficulty_spinner)

        form_card.add_widget(BodyLabel(text="Тип комнаты"))
        self.visibility_spinner = RoomSpinner(
            "Выбери тип комнаты",
            ["Открытая (по коду)", "Публичная (в списке)"],
        )
        form_card.add_widget(self.visibility_spinner)

        form_card.add_widget(BodyLabel(text="Таймер раунда"))
        self.round_timer_spinner = RoomSpinner(
            "Выбери таймер",
            ["30 сек", "45 сек", "60 сек", "75 сек", "90 сек", "120 сек"],
        )
        form_card.add_widget(self.round_timer_spinner)

        form_card.add_widget(BodyLabel(text="Количество раундов"))
        self.rounds_spinner = RoomSpinner(
            "Выбери число раундов",
            [str(number) for number in range(3, 11)],
        )
        form_card.add_widget(self.rounds_spinner)

        form_card.add_widget(
            BodyLabel(
                color=COLORS["text_muted"],
                text="Комната появится в общем списке, если выбрать публичный тип.",
            )
        )
        content.add_widget(form_card)

        actions = BoxLayout(orientation="vertical", spacing=dp(10), size_hint_y=None)
        actions.bind(minimum_height=actions.setter("height"))
        create_btn = AppButton(text="Создать комнату", font_size=sp(18))
        create_btn.bind(on_release=self.prepare_room)
        actions.add_widget(create_btn)
        self.status_label = BodyLabel(
            center=True,
            color=COLORS["text_muted"],
            text="Заполни параметры комнаты, и мы создадим онлайн-лобби.",
        )
        actions.add_widget(self.status_label)

        self.open_list_btn = AppButton(text="К списку комнат", compact=True, font_size=sp(14))
        self.open_list_btn.height = dp(44)
        self.open_list_btn.opacity = 0
        self.open_list_btn.disabled = True
        self.open_list_btn.bind(on_release=lambda *_: setattr(self.manager, "current", "join_room"))
        actions.add_widget(self.open_list_btn)
        content.add_widget(actions)

        root.add_widget(scroll)
        self.coin_badge = CoinBadge(pos_hint={"right": 0.965, "top": 0.96})
        root.add_widget(self.coin_badge)
        self.add_widget(root)

    def on_pre_enter(self, *_):
        app = App.get_running_app()
        player_name = app.resolve_player_name() if app is not None else None
        profile = app.current_profile() if app is not None else None
        self.coin_badge.refresh_from_session()
        if not player_name:
            self.profile_name_label.color = COLORS["warning"]
            self.profile_name_label.text = "Сначала войди в аккаунт или начни гостевую сессию."
            self.coin_balance_label.color = COLORS["text_muted"]
            self.coin_balance_label.text = f"Создание комнаты стоит {ROOM_CREATION_COST} Alias Coin."
            return

        if profile is None:
            self.profile_name_label.color = COLORS["warning"]
            self.profile_name_label.text = "Гость может только присоединяться к комнатам."
            self.coin_balance_label.color = COLORS["warning"]
            self.coin_balance_label.text = f"Чтобы создать комнату, войди в аккаунт и накопи {ROOM_CREATION_COST} Alias Coin."
            return

        self.profile_name_label.color = COLORS["accent"]
        self.profile_name_label.text = f"Комната будет создана от имени: {player_name}"
        self.coin_balance_label.color = COLORS["text_muted"]
        self.coin_balance_label.text = (
            f"Баланс: {profile.alias_coins} Alias Coin. "
            f"Создание комнаты стоит {ROOM_CREATION_COST}."
        )

    def _timer_to_seconds(self, timer_value):
        return int((timer_value or "").split()[0])

    def _set_join_list_button(self, enabled):
        self.open_list_btn.disabled = not enabled
        self.open_list_btn.opacity = 1 if enabled else 0
        self.open_list_btn.height = dp(44) if enabled else 0

    def prepare_room(self, *_):
        app = App.get_running_app()
        player_name = app.resolve_player_name() if app is not None else None
        profile = app.current_profile() if app is not None else None
        room_name = self.room_name_input.text.strip()
        players = self.players_spinner.selected_value()
        difficulty = self.difficulty_spinner.selected_value()
        visibility = self.visibility_spinner.selected_value()
        round_timer = self.round_timer_spinner.selected_value()
        rounds = self.rounds_spinner.selected_value()

        self._set_join_list_button(False)

        if not player_name:
            self.status_label.color = COLORS["error"]
            self.status_label.text = "Сначала начни сессию через вход, регистрацию или гостевой режим."
            return

        if profile is None:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = (
                f"Гостевой режим не может создавать комнаты. "
                f"Войди в аккаунт и накопи {ROOM_CREATION_COST} Alias Coin."
            )
            return

        if profile.alias_coins < ROOM_CREATION_COST:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = (
                f"Недостаточно Alias Coin. Нужно {ROOM_CREATION_COST}, "
                f"а у тебя сейчас {profile.alias_coins}."
            )
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

        if not visibility:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Выбери тип комнаты."
            return

        if not round_timer:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Выбери таймер раунда."
            return

        if not rounds:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Выбери количество раундов."
            return

        try:
            room = create_online_room(
                host_name=player_name,
                room_name=room_name,
                max_players=int(players),
                difficulty=difficulty,
                visibility=visibility,
                visibility_scope="public" if visibility.startswith("Публичная") else "private",
                round_timer_sec=self._timer_to_seconds(round_timer),
                rounds=int(rounds),
            )
        except ConnectionError as error:
            self.status_label.color = COLORS["error"]
            self.status_label.text = str(error)
            return
        except ValueError as error:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = str(error)
            return

        self.pending_room_config = room
        try:
            updated_profile = spend_alias_coins(email=profile.email, amount=ROOM_CREATION_COST)
        except ValueError:
            updated_profile = profile
        self.coin_badge.set_value(updated_profile.alias_coins)
        self.status_label.color = COLORS["success"]
        self.status_label.text = (
            f"Комната '{room.get('room_name', room_name)}' создана. "
            f"Код: {room.get('code', '----')}. "
            f"Осталось {updated_profile.alias_coins} Alias Coin."
        )
        self._set_join_list_button(True)
        if app is not None:
            app.set_active_room(room)
        self.manager.current = "room"
