from kivy.app import App
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from services import join_online_room, list_online_rooms
from ui import (
    AppButton,
    AppTextInput,
    BodyLabel,
    BrandTitle,
    CoinBadge,
    COLORS,
    IconCircleButton,
    IconMetaChip,
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
        self._room_access_locked = False

        root = ScreenBackground()
        scroll, content = build_scrollable_content(padding=[dp(20), dp(20), dp(20), dp(24)], spacing=12)

        top_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(50))
        back_btn = AppButton(text="Назад", compact=True, size_hint=(None, None), size=(dp(126), dp(46)))
        back_btn.bind(on_release=lambda *_: setattr(self.manager, "current", "start"))
        top_row.add_widget(back_btn)
        top_row.add_widget(Widget())
        content.add_widget(top_row)

        content.add_widget(BrandTitle(text="ALIAS ONLINE", height=dp(92), font_size=sp(34), shadow_step=dp(3)))
        content.add_widget(PixelLabel(text="Войти в комнату", font_size=sp(21), center=True, size_hint_y=None))

        code_card = RoundedPanel(
            orientation="vertical",
            padding=[dp(16), dp(16), dp(16), dp(16)],
            spacing=dp(12),
            size_hint_y=None,
            bg_color=COLORS["surface_card"],
            shadow_alpha=0.14,
        )
        code_card.bind(minimum_height=code_card.setter("height"))
        code_card.add_widget(PixelLabel(text="Вход по коду", font_size=sp(15), center=True, size_hint_y=None))

        code_row = BoxLayout(orientation="horizontal", spacing=dp(10), size_hint_y=None, height=dp(48))
        self.room_code_input = AppTextInput(hint_text="Код комнаты", height=dp(48))
        code_row.add_widget(self.room_code_input)
        self.join_btn = AppButton(text="Войти", compact=True, font_size=sp(14), size_hint=(None, None), size=(dp(112), dp(46)))
        self.join_btn.bind(on_release=self._join_from_input)
        code_row.add_widget(self.join_btn)
        code_card.add_widget(code_row)
        content.add_widget(code_card)

        self.rooms_card = RoundedPanel(
            orientation="vertical",
            padding=[dp(16), dp(16), dp(16), dp(16)],
            spacing=dp(12),
            size_hint_y=None,
            bg_color=COLORS["surface_card"],
            shadow_alpha=0.12,
        )
        self.rooms_card.bind(minimum_height=self.rooms_card.setter("height"))

        rooms_header = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(38), spacing=dp(10))
        rooms_header.add_widget(PixelLabel(text="Публичные комнаты", font_size=sp(15), size_hint=(1, None), center=False))
        self.refresh_btn = IconCircleButton(icon="refresh", size=(dp(38), dp(38)))
        self.refresh_btn.bind(on_release=lambda *_: self.refresh_room_list())
        rooms_header.add_widget(self.refresh_btn)
        self.rooms_card.add_widget(rooms_header)

        self.rooms_box = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None)
        self.rooms_box.bind(minimum_height=self.rooms_box.setter("height"))
        self.rooms_card.add_widget(self.rooms_box)
        content.add_widget(self.rooms_card)

        self.status_label = BodyLabel(
            center=True,
            color=COLORS["text_muted"],
            font_size=sp(11.5),
            text="Введи код комнаты или выбери подходящую комнату из списка ниже.",
            size_hint_y=None,
        )
        content.add_widget(self.status_label)

        root.add_widget(scroll)
        self.coin_badge = CoinBadge(pos_hint={"right": 0.965, "top": 0.96})
        root.add_widget(self.coin_badge)
        self.add_widget(root)

    def _room_access_message(self, remaining_seconds):
        minutes = max(1, (int(remaining_seconds) + 59) // 60)
        return f"После выхода из матча вход в комнаты временно закрыт. Подожди примерно {minutes} мин."

    def on_pre_enter(self, *_):
        app = App.get_running_app()
        player_name = app.resolve_player_name() if app is not None else None
        room_access_state = app.room_access_state() if app is not None and hasattr(app, "room_access_state") else {"active": False}
        self._room_access_locked = bool(room_access_state.get("active"))
        self.coin_badge.refresh_from_session()
        self.join_btn.disabled = self._room_access_locked
        self.room_code_input.disabled = self._room_access_locked

        if not player_name:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Сначала войди в аккаунт или начни гостевую сессию."
            self.rooms_cache = []
            self._render_rooms()
            return

        if self._room_access_locked:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = self._room_access_message(room_access_state.get("remaining_seconds", 0))
        else:
            self.status_label.color = COLORS["text_muted"]
            self.status_label.text = "Введи код комнаты или выбери подходящую комнату из списка ниже."

        self.refresh_room_list()

    def _normalize_code(self, raw_code):
        return "".join(character for character in (raw_code or "").upper() if character.isalnum())

    def _empty_rooms_note(self, text):
        note_card = RoundedPanel(
            orientation="vertical",
            padding=[dp(14), dp(14), dp(14), dp(14)],
            spacing=dp(6),
            size_hint_y=None,
            bg_color=COLORS["surface_soft"],
            shadow_alpha=0.06,
        )
        note_card.bind(minimum_height=note_card.setter("height"))
        note_card._border_color.rgba = COLORS["outline_soft"]
        note_card._border_line.width = 1.0
        note_card.add_widget(
            BodyLabel(
                center=True,
                color=COLORS["text_muted"],
                font_size=sp(11),
                text=text,
                size_hint_y=None,
            )
        )
        return note_card

    def _render_rooms(self):
        self.rooms_box.clear_widgets()

        if not self.rooms_cache:
            self.rooms_box.add_widget(self._empty_rooms_note("Пока нет публичных комнат. Можно создать первую."))
            return

        for room in self.rooms_cache:
            title_text = (room.get("room_name") or "").strip() or (room.get("host_name") or "Комната")
            host_name = (room.get("host_name") or "").strip() or "—"
            player_count_text = f"{room.get('players_count', 0)}/{room.get('max_players', 0)}"
            code_text = room.get("code", "----")

            row = RoundedPanel(
                orientation="vertical",
                padding=[dp(14), dp(12), dp(14), dp(12)],
                spacing=dp(8),
                size_hint_y=None,
                bg_color=COLORS["surface_soft"],
                shadow_alpha=0.08,
            )
            row.bind(minimum_height=row.setter("height"))
            row._border_color.rgba = COLORS["outline_soft"]
            row._border_line.width = 1.0

            header_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(36), spacing=dp(8))
            title_box = BoxLayout(orientation="vertical", spacing=dp(0))
            title_box.add_widget(
                PixelLabel(
                    text=title_text,
                    font_size=sp(14),
                    size_hint_y=None,
                    shorten=True,
                    shorten_from="right",
                    max_lines=1,
                )
            )
            title_box.add_widget(
                BodyLabel(
                    text=f"Хост: {host_name}",
                    color=COLORS["text_muted"],
                    font_size=sp(10.5),
                    size_hint_y=None,
                )
            )
            header_row.add_widget(title_box)

            join_btn = AppButton(
                text="Войти",
                compact=True,
                font_size=sp(13),
                size_hint=(None, None),
                size=(dp(92), dp(34)),
            )
            join_btn.bind(on_release=lambda *_args, room_code=code_text: self._join_by_code(room_code))
            join_btn.disabled = self._room_access_locked
            join_btn.opacity = 0.72 if self._room_access_locked else 1
            header_row.add_widget(join_btn)
            row.add_widget(header_row)

            meta_row = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(30))
            players_chip = IconMetaChip(icon="users", text=player_count_text)
            code_chip = IconMetaChip(icon="code", text=code_text)
            meta_row.add_widget(players_chip)
            meta_row.add_widget(code_chip)
            meta_row.add_widget(Widget())
            row.add_widget(meta_row)

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

        if self._room_access_locked:
            app = App.get_running_app()
            room_access_state = app.room_access_state() if app is not None and hasattr(app, "room_access_state") else {"remaining_seconds": 0}
            self.status_label.color = COLORS["warning"]
            self.status_label.text = self._room_access_message(room_access_state.get("remaining_seconds", 0))
        else:
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
        room_access_state = app.room_access_state() if app is not None and hasattr(app, "room_access_state") else {"active": False, "remaining_seconds": 0}

        if room_access_state.get("active"):
            self.status_label.color = COLORS["warning"]
            self.status_label.text = self._room_access_message(room_access_state.get("remaining_seconds", 0))
            return

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
            f"Ты в комнате «{joined_room.get('room_name', code)}». "
            f"Игроков: {joined_room.get('players_count', '?')}/{joined_room.get('max_players', '?')}."
        )
        if app is not None:
            app.set_active_room(joined_room)
        self.manager.current = "room"
