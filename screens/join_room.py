from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget
from threading import Thread

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
    LoadingOverlay,
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
        self._room_access_event = None
        self.room_access_popup = None
        self.room_access_popup_message_label = None
        self._refresh_in_progress = False
        self._refresh_token = 0
        self._join_in_progress = False
        self._join_request_token = 0

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
            spacing=dp(10),
            size_hint_y=None,
            bg_color=COLORS["surface_card"],
            shadow_alpha=0.10,
        )
        self.rooms_card.bind(minimum_height=self.rooms_card.setter("height"))

        rooms_header = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(34), spacing=dp(8))
        rooms_header.add_widget(PixelLabel(text="Публичные комнаты", font_size=sp(15), size_hint=(1, None), center=False))
        self.refresh_btn = IconCircleButton(icon="refresh", size=(dp(34), dp(34)))
        self.refresh_btn.bind(on_press=self._handle_refresh_press)
        rooms_header.add_widget(self.refresh_btn)
        self.rooms_card.add_widget(rooms_header)

        self.rooms_box = BoxLayout(orientation="vertical", spacing=dp(10), size_hint_y=None)
        self.rooms_box.bind(minimum_height=self.rooms_box.setter("height"))
        self.rooms_card.add_widget(self.rooms_box)
        content.add_widget(self.rooms_card)

        self.status_card = RoundedPanel(
            orientation="vertical",
            padding=[dp(14), dp(12), dp(14), dp(12)],
            spacing=dp(6),
            size_hint_y=None,
            bg_color=COLORS["surface_soft"],
            shadow_alpha=0.06,
        )
        self.status_card.bind(minimum_height=self.status_card.setter("height"))
        self.status_card._border_color.rgba = COLORS["outline_soft"]
        self.status_card._border_line.width = 1.0
        self.status_label = BodyLabel(
            center=True,
            color=COLORS["text_muted"],
            font_size=sp(11.5),
            text="Введи код комнаты или выбери подходящую комнату из списка ниже.",
            size_hint_y=None,
        )
        self.status_card.add_widget(self.status_label)
        content.add_widget(self.status_card)

        root.add_widget(scroll)
        self.coin_badge = CoinBadge(pos_hint={"right": 0.965, "top": 0.96})
        root.add_widget(self.coin_badge)
        self.loading_overlay = LoadingOverlay()
        root.add_widget(self.loading_overlay)
        self.add_widget(root)

    def _room_access_message(self, remaining_seconds):
        app = App.get_running_app()
        if app is not None and hasattr(app, "format_room_access_message"):
            return app.format_room_access_message("Вход в комнату")
        minutes = max(1, (int(remaining_seconds) + 59) // 60)
        return f"Вход в комнату сейчас недоступен. Подожди примерно {minutes} мин."

    def on_pre_enter(self, *_):
        app = App.get_running_app()
        player_name = app.resolve_player_name() if app is not None else None
        room_access_state = app.room_access_state() if app is not None and hasattr(app, "room_access_state") else {"active": False}
        self._room_access_locked = bool(room_access_state.get("active"))
        self._join_in_progress = False
        self.loading_overlay.hide()
        self.coin_badge.refresh_from_session()
        self._apply_room_access_ui()
        self._start_room_access_watch()

        if not player_name:
            self._set_status("Сначала войди в аккаунт или начни гостевую сессию.", COLORS["warning"], "warning")
            self.rooms_cache = []
            self._render_rooms()
            return

        if self._room_access_locked:
            self._set_status(self._room_access_message(room_access_state.get("remaining_seconds", 0)), COLORS["warning"], "warning")
        else:
            self._set_status("Введи код комнаты или выбери подходящую комнату из списка ниже.", COLORS["text_muted"], "neutral")

        self.refresh_room_list()

    def on_leave(self, *_):
        self._stop_room_access_watch()
        self._refresh_token += 1
        self._join_request_token += 1
        self._refresh_in_progress = False
        self._join_in_progress = False
        self.join_btn.disabled = False
        self.loading_overlay.hide()
        self.refresh_btn.stop_spinning()
        self._dismiss_room_access_popup()

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
        if locked != self._room_access_locked:
            self._room_access_locked = locked
            self.refresh_room_list()
        self._apply_room_access_ui()
        self._update_room_access_popup_message(state)
        if locked:
            self._set_status(self._room_access_message(state.get("remaining_seconds", 0)), COLORS["warning"], "warning")

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

    def _set_join_button_locked(self, button, locked):
        if locked:
            button._rest_button_color = COLORS["danger_button"]
            button._pressed_button_color = COLORS["danger_button_pressed"]
            button._border_color.rgba = (1, 0.82, 0.82, 0.30)
        else:
            button._rest_button_color = COLORS["button"]
            button._pressed_button_color = COLORS["button_pressed"]
            button._border_color.rgba = COLORS["outline"]
        button._button_color.rgba = button._rest_button_color
        button.opacity = 1

    def _apply_room_access_ui(self):
        self._set_join_button_locked(self.join_btn, self._room_access_locked)

    def _set_status(self, text, color=None, tone="neutral"):
        self.status_label.text = text
        self.status_label.color = color or COLORS["text_muted"]
        if tone == "warning":
            self.status_card._bg_color.rgba = (0.27, 0.13, 0.10, 0.82)
            self.status_card._border_color.rgba = (1, 0.80, 0.60, 0.22)
        elif tone == "error":
            self.status_card._bg_color.rgba = (0.30, 0.10, 0.12, 0.88)
            self.status_card._border_color.rgba = (1, 0.74, 0.74, 0.30)
        elif tone == "success":
            self.status_card._bg_color.rgba = (0.10, 0.23, 0.18, 0.76)
            self.status_card._border_color.rgba = (0.72, 1, 0.82, 0.24)
        else:
            self.status_card._bg_color.rgba = COLORS["surface_soft"]
            self.status_card._border_color.rgba = COLORS["outline_soft"]

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
        panel.add_widget(PixelLabel(text="Вход временно закрыт", font_size=sp(18), center=True, size_hint_y=None))

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
                size=(dp(88), dp(34)),
            )
            join_btn.bind(on_release=lambda *_args, room_code=code_text: self._join_by_code(room_code))
            self._set_join_button_locked(join_btn, self._room_access_locked)
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

    def _handle_refresh_press(self, *_):
        self.refresh_room_list(from_user=True)

    def refresh_room_list(self, from_user=False):
        if self._refresh_in_progress:
            return

        self._refresh_in_progress = True
        self._refresh_token += 1
        request_token = self._refresh_token
        self.refresh_btn.start_spinning()

        if from_user and not self._room_access_locked:
            self._set_status("Обновляем список публичных комнат...", COLORS["text_muted"], "neutral")

        worker = Thread(target=self._load_rooms_worker, args=(request_token,), daemon=True)
        worker.start()

    def _load_rooms_worker(self, request_token):
        try:
            rooms = list_online_rooms(public_only=True)
            payload = {"status": "success", "rooms": rooms}
        except ConnectionError as error:
            payload = {"status": "connection_error", "message": str(error)}
        except ValueError as error:
            payload = {"status": "value_error", "message": str(error)}

        Clock.schedule_once(lambda _dt, token=request_token, result=payload: self._finish_room_list_refresh(token, result))

    def _finish_room_list_refresh(self, request_token, payload):
        if request_token != self._refresh_token:
            return

        self._refresh_in_progress = False
        self.refresh_btn.stop_spinning()

        status = payload.get("status")
        if status == "success":
            self.rooms_cache = list(payload.get("rooms") or [])
        else:
            self.rooms_cache = []
            message = payload.get("message") or "Не удалось обновить список комнат."
            if status == "connection_error":
                self._set_status(message, COLORS["error"], "error")
            else:
                self._set_status(message, COLORS["warning"], "warning")
            self._render_rooms()
            return

        if self._room_access_locked:
            app = App.get_running_app()
            room_access_state = app.room_access_state() if app is not None and hasattr(app, "room_access_state") else {"remaining_seconds": 0}
            self._set_status(self._room_access_message(room_access_state.get("remaining_seconds", 0)), COLORS["warning"], "warning")
        else:
            self._set_status(f"Найдено публичных комнат: {len(self.rooms_cache)}", COLORS["text_muted"], "neutral")
        self._render_rooms()

    def _join_from_input(self, *_):
        code = self._normalize_code(self.room_code_input.text)
        self.room_code_input.text = code
        self._join_by_code(code)

    def _join_by_code(self, code):
        if self._join_in_progress:
            return
        app = App.get_running_app()
        if app is not None and hasattr(app, "_start_room_server_in_background"):
            app._start_room_server_in_background()
        player_name = app.resolve_player_name() if app is not None else None
        room_access_state = app.room_access_state() if app is not None and hasattr(app, "room_access_state") else {"active": False, "remaining_seconds": 0}

        if room_access_state.get("active"):
            self._set_status(self._room_access_message(room_access_state.get("remaining_seconds", 0)), COLORS["warning"], "warning")
            self._open_room_access_popup()
            return

        if not player_name:
            self._set_status("Сначала начни сессию через вход, регистрацию или гостевой режим.", COLORS["error"], "error")
            return

        if len(code) < 4:
            self._set_status("Введи корректный код комнаты.", COLORS["warning"], "warning")
            return

        self._start_join_request(code=code, player_name=player_name)
        return

        self._join_in_progress = True
        self.join_btn.disabled = True
        self.loading_overlay.show("Подключаем к комнате...")
        try:
            joined_room = join_online_room(room_code=code, player_name=player_name)
        except ConnectionError as error:
            self._set_status(str(error), COLORS["error"], "error")
            self._join_in_progress = False
            self.join_btn.disabled = False
            self.loading_overlay.hide()
            return
        except ValueError as error:
            self._set_status(str(error), COLORS["warning"], "warning")
            self._join_in_progress = False
            self.join_btn.disabled = False
            self.loading_overlay.hide()
            return

        self._join_in_progress = False
        self.join_btn.disabled = False
        self.loading_overlay.hide()
        self.joined_room = joined_room
        self._set_status(
            f"Ты в комнате «{joined_room.get('room_name', code)}». "
            f"Игроков: {joined_room.get('players_count', '?')}/{joined_room.get('max_players', '?')}.",
            COLORS["success"],
            "success",
        )
        if app is not None:
            app.set_active_room(joined_room)
            if hasattr(app, "ensure_screen"):
                app.ensure_screen("room")
        self.manager.current = "room"

    def _start_join_request(self, *, code, player_name):
        self._join_in_progress = True
        self._join_request_token += 1
        request_token = self._join_request_token
        self.join_btn.disabled = True
        self.loading_overlay.show("Подключаем к комнате...")

        worker = Thread(
            target=self._join_by_code_worker,
            args=(request_token, code, player_name),
            daemon=True,
        )
        worker.start()

    def _join_by_code_worker(self, request_token, room_code, player_name):
        try:
            joined_room = join_online_room(room_code=room_code, player_name=player_name)
            payload = {"status": "success", "room": joined_room, "room_code": room_code}
        except ConnectionError as error:
            payload = {"status": "error", "tone": "error", "message": str(error)}
        except ValueError as error:
            payload = {"status": "error", "tone": "warning", "message": str(error)}
        except Exception as error:
            payload = {"status": "error", "tone": "error", "message": f"Неожиданная ошибка: {error}"}

        Clock.schedule_once(lambda _dt, token=request_token, result=payload: self._finish_join_request(token, result))

    def _finish_join_request(self, request_token, payload):
        if request_token != self._join_request_token:
            return

        self._join_in_progress = False
        self.join_btn.disabled = False
        self.loading_overlay.hide()

        if payload.get("status") != "success":
            tone = payload.get("tone", "error")
            color = COLORS["warning"] if tone == "warning" else COLORS["error"]
            self._set_status(payload.get("message") or "Не удалось войти в комнату.", color, tone)
            return

        joined_room = payload.get("room") or {}
        room_code = payload.get("room_code") or "----"
        self.joined_room = joined_room
        self._set_status(
            f"Ты в комнате «{joined_room.get('room_name', room_code)}». "
            f"Игроков: {joined_room.get('players_count', '?')}/{joined_room.get('max_players', '?')}.",
            COLORS["success"],
            "success",
        )

        app = App.get_running_app()
        if app is not None:
            app.set_active_room(joined_room)
            if hasattr(app, "ensure_screen"):
                app.ensure_screen("room")
        if self.manager is not None:
            self.manager.current = "room"
