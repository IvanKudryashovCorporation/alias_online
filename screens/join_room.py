from kivy.app import App
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from services import join_online_room, list_online_rooms, room_server_url
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


class JoinRoomScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        register_game_font()
        self.rooms_cache = []
        self.joined_room = None

        root = ScreenBackground()
        scroll, content = build_scrollable_content(padding=[dp(20), dp(24), dp(20), dp(20)], spacing=10)

        back_btn = AppButton(text="Назад", compact=True, size_hint_x=None, width=dp(132))
        back_btn.bind(on_release=lambda *_: setattr(self.manager, "current", "start"))
        content.add_widget(back_btn)
        content.add_widget(BrandTitle(text="ALIAS ONLINE", height=dp(116), font_size=sp(40), shadow_step=dp(3)))
        content.add_widget(PixelLabel(text="Войти в комнату", font_size=sp(20), center=True))

        session_card = RoundedPanel(
            orientation="vertical",
            padding=[dp(16), dp(14), dp(16), dp(14)],
            spacing=dp(8),
            size_hint_y=None,
        )
        session_card.bind(minimum_height=session_card.setter("height"))
        session_card.add_widget(BodyLabel(text="Игрок"))
        self.profile_name_label = BodyLabel(
            color=COLORS["accent"],
            text="Имя подтянется из текущей сессии.",
        )
        session_card.add_widget(self.profile_name_label)
        self.server_label = BodyLabel(
            color=COLORS["text_muted"],
            font_size=sp(11),
            text=f"Сервер комнат: {room_server_url()}",
        )
        session_card.add_widget(self.server_label)
        content.add_widget(session_card)

        code_card = RoundedPanel(
            orientation="vertical",
            padding=[dp(16), dp(14), dp(16), dp(14)],
            spacing=dp(8),
            size_hint_y=None,
        )
        code_card.bind(minimum_height=code_card.setter("height"))
        code_card.add_widget(PixelLabel(text="Вход по коду", font_size=sp(13), center=True))
        self.room_code_input = AppTextInput(hint_text="Например, AB12CD", height=dp(48))
        code_card.add_widget(self.room_code_input)

        code_buttons = BoxLayout(orientation="horizontal", spacing=dp(10), size_hint_y=None, height=dp(54))
        join_btn = AppButton(text="Войти", compact=True, font_size=sp(14))
        join_btn.bind(on_release=self._join_from_input)
        refresh_btn = AppButton(text="Обновить список", compact=True, font_size=sp(14))
        refresh_btn.bind(on_release=lambda *_: self.refresh_room_list())
        code_buttons.add_widget(join_btn)
        code_buttons.add_widget(refresh_btn)
        code_card.add_widget(code_buttons)
        content.add_widget(code_card)

        rooms_card = RoundedPanel(
            orientation="vertical",
            padding=[dp(16), dp(14), dp(16), dp(14)],
            spacing=dp(10),
            size_hint_y=None,
        )
        rooms_card.bind(minimum_height=rooms_card.setter("height"))
        rooms_card.add_widget(PixelLabel(text="Публичные комнаты", font_size=sp(13), center=True))

        self.rooms_box = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None)
        self.rooms_box.bind(minimum_height=self.rooms_box.setter("height"))
        rooms_card.add_widget(self.rooms_box)
        content.add_widget(rooms_card)

        self.status_label = BodyLabel(
            center=True,
            color=COLORS["text_muted"],
            text="Можно войти по коду или выбрать комнату из списка.",
            size_hint_y=None,
        )
        content.add_widget(self.status_label)

        root.add_widget(scroll)
        self.add_widget(root)

    def on_pre_enter(self, *_):
        app = App.get_running_app()
        player_name = app.resolve_player_name() if app is not None else None
        if not player_name:
            self.profile_name_label.color = COLORS["warning"]
            self.profile_name_label.text = "Сначала войди в аккаунт или начни гостевую сессию."
            self.rooms_cache = []
            self._render_rooms()
            return

        self.profile_name_label.color = COLORS["accent"]
        self.profile_name_label.text = f"Вход в комнату будет под именем: {player_name}"
        self.refresh_room_list()

    def _normalize_code(self, raw_code):
        return "".join(character for character in (raw_code or "").upper() if character.isalnum())

    def _render_rooms(self):
        self.rooms_box.clear_widgets()

        if not self.rooms_cache:
            empty_note = BodyLabel(
                center=True,
                color=COLORS["text_muted"],
                text="Пока нет публичных комнат. Создай первую.",
                size_hint_y=None,
            )
            self.rooms_box.add_widget(empty_note)
            return

        for room in self.rooms_cache:
            row = RoundedPanel(
                orientation="vertical",
                padding=[dp(12), dp(10), dp(12), dp(10)],
                spacing=dp(6),
                size_hint_y=None,
            )
            row.bind(minimum_height=row.setter("height"))

            title = PixelLabel(
                text=f"{room['room_name']} ({room['players_count']}/{room['max_players']})",
                center=True,
                font_size=sp(14),
                size_hint_y=None,
            )
            row.add_widget(title)

            details = BodyLabel(
                center=True,
                color=COLORS["text_muted"],
                font_size=sp(11),
                text=(
                    f"Код: {room['code']} | {room['difficulty']} | "
                    f"{room['rounds']} раундов по {room['round_timer_sec']} сек | Хост: {room['host_name']}"
                ),
                size_hint_y=None,
            )
            row.add_widget(details)

            button_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(44))
            button_row.add_widget(Widget())
            join_btn = AppButton(text="Войти в эту комнату", compact=True, font_size=sp(13), size_hint=(None, None), size=(dp(220), dp(40)))
            join_btn.bind(on_release=lambda *_args, room_code=room["code"]: self._join_by_code(room_code))
            button_row.add_widget(join_btn)
            button_row.add_widget(Widget())
            row.add_widget(button_row)

            self.rooms_box.add_widget(row)

    def refresh_room_list(self):
        try:
            self.rooms_cache = list_online_rooms(public_only=True)
        except ConnectionError as error:
            self.rooms_cache = []
            self.status_label.color = COLORS["error"]
            self.status_label.text = str(error)
            self._render_rooms()
            return
        except ValueError as error:
            self.rooms_cache = []
            self.status_label.color = COLORS["warning"]
            self.status_label.text = str(error)
            self._render_rooms()
            return

        self.status_label.color = COLORS["text_muted"]
        self.status_label.text = f"Найдено публичных комнат: {len(self.rooms_cache)}"
        self._render_rooms()

    def _join_from_input(self, *_):
        code = self._normalize_code(self.room_code_input.text)
        self.room_code_input.text = code
        self._join_by_code(code)

    def _join_by_code(self, code):
        app = App.get_running_app()
        player_name = app.resolve_player_name() if app is not None else None

        if not player_name:
            self.status_label.color = COLORS["error"]
            self.status_label.text = "Сначала начни сессию через вход, регистрацию или гостевой режим."
            return

        if len(code) < 4:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Введи корректный код комнаты."
            return

        try:
            joined_room = join_online_room(room_code=code, player_name=player_name)
        except ConnectionError as error:
            self.status_label.color = COLORS["error"]
            self.status_label.text = str(error)
            return
        except ValueError as error:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = str(error)
            return

        self.joined_room = joined_room
        self.status_label.color = COLORS["success"]
        self.status_label.text = (
            f"Ты в комнате '{joined_room.get('room_name', code)}'. "
            f"Игроков: {joined_room.get('players_count', '?')}/{joined_room.get('max_players', '?')}."
        )
        if app is not None:
            app.set_active_room(joined_room)
        self.manager.current = "room"
