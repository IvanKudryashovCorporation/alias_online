import time

from kivy.app import App
from kivy.clock import Clock
from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from services import (
    RoomVoiceEngine,
    get_online_room_state,
    ping_room_voice,
    send_room_guess,
    skip_room_word,
    start_room_game,
)
from ui import (
    AppButton,
    AppTextInput,
    BodyLabel,
    BrandTitle,
    COLORS,
    PixelLabel,
    RoundedPanel,
    ScreenBackground,
    register_game_font,
)


class VoiceMicButton(ButtonBehavior, Widget):
    def __init__(self, **kwargs):
        super().__init__(size_hint=(None, None), size=(dp(94), dp(94)), **kwargs)
        self._muted = True
        self._enabled = True
        self._level = 0.0

        with self.canvas.before:
            self._shadow_color = Color(0, 0, 0, 0.22)
            self._shadow = Ellipse(pos=self.pos, size=self.size)
            self._bg_color = Color(0.08, 0.13, 0.21, 0.96)
            self._bg = Ellipse(pos=self.pos, size=self.size)

            self._mic_color = Color(0.96, 0.98, 1.0, 1.0)
            self._capsule = RoundedRectangle(radius=[dp(10)] * 4)
            self._support_arc = Line(width=dp(2.8), ellipse=(self.x, self.y, self.width, self.height, 205, 335))
            self._stem = RoundedRectangle(radius=[dp(2)] * 4)
            self._base = RoundedRectangle(radius=[dp(2)] * 4)
            self._capsule_cut_color = Color(0.08, 0.13, 0.21, 1.0)
            self._capsule_cut = RoundedRectangle(radius=[dp(4)] * 4)

            self._outline_color = Color(1, 1, 1, 0.2)
            self._outline = Line(width=1.2, ellipse=(self.x, self.y, self.width, self.height))

            self._mute_color = Color(0.96, 0.23, 0.23, 0.0)
            self._mute_line = Line(width=dp(3.2), points=[])

        self.bind(pos=self._sync_canvas, size=self._sync_canvas)

    @property
    def muted(self):
        return self._muted

    def set_muted(self, muted):
        self._muted = bool(muted)
        self._refresh_state()

    def set_enabled(self, enabled):
        self._enabled = bool(enabled)
        self._refresh_state()

    def set_level(self, level):
        self._level = max(0.0, min(1.0, float(level)))
        self._refresh_state()

    def on_press(self):
        if not self._enabled:
            return
        self._bg_color.rgba = (0.06, 0.10, 0.16, 0.96)

    def on_release(self):
        self._refresh_state()

    def _refresh_state(self):
        if not self._enabled:
            self._bg_color.rgba = (0.14, 0.14, 0.16, 0.82)
            self._mic_color.rgba = (0.65, 0.68, 0.72, 1.0)
            self._capsule_cut_color.rgba = (0.14, 0.14, 0.16, 1.0)
            self._mute_color.rgba = (0.96, 0.23, 0.23, 0.42)
        else:
            self._bg_color.rgba = (0.08, 0.13, 0.21, 0.96)
            self._capsule_cut_color.rgba = (0.08, 0.13, 0.21, 1.0)
            if self._muted:
                self._mic_color.rgba = (0.96, 0.98, 1.0, 1.0)
            else:
                # Fill the mic icon itself with green based on speech level.
                level = self._level
                red = 0.96 * (1 - level) + 0.21 * level
                green = 0.98 * (1 - level) + 0.90 * level
                blue = 1.00 * (1 - level) + 0.36 * level
                self._mic_color.rgba = (red, green, blue, 1.0)
            self._mute_color.rgba = (0.96, 0.23, 0.23, 0.95 if self._muted else 0.0)

        self._sync_canvas()

    def _sync_canvas(self, *_):
        self._shadow.pos = (self.x, self.y - dp(2))
        self._shadow.size = self.size
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._outline.ellipse = (self.x, self.y, self.width, self.height)

        capsule_w = self.width * 0.27
        capsule_h = self.height * 0.36
        self._capsule.pos = (self.center_x - capsule_w / 2, self.y + self.height * 0.50 - capsule_h / 2)
        self._capsule.size = (capsule_w, capsule_h)

        cut_w = capsule_w * 0.18
        cut_h = capsule_h * 0.44
        self._capsule_cut.pos = (self.center_x - cut_w / 2, self._capsule.pos[1] + capsule_h * 0.32)
        self._capsule_cut.size = (cut_w, cut_h)

        arc_w = self.width * 0.44
        arc_h = self.height * 0.40
        arc_x = self.center_x - arc_w / 2
        arc_y = self.y + self.height * 0.27
        self._support_arc.ellipse = (arc_x, arc_y, arc_w, arc_h, 205, 335)

        stem_w = self.width * 0.055
        stem_h = self.height * 0.12
        self._stem.pos = (self.center_x - stem_w / 2, self.y + self.height * 0.28)
        self._stem.size = (stem_w, stem_h)

        base_w = self.width * 0.30
        base_h = self.height * 0.05
        self._base.pos = (self.center_x - base_w / 2, self.y + self.height * 0.21)
        self._base.size = (base_w, base_h)

        self._mute_line.points = [
            self.x + self.width * 0.24,
            self.y + self.height * 0.26,
            self.x + self.width * 0.76,
            self.y + self.height * 0.74,
        ]


class FullscreenCountdownOverlay(FloatLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._active = False
        with self.canvas.before:
            self._shade_color = Color(0, 0, 0, 0.78)
            self._shade_rect = Rectangle(pos=self.pos, size=self.size)

        self._label = Label(
            text="",
            font_name="BrandFont",
            font_size=sp(132),
            color=(1, 1, 1, 1),
            halign="center",
            valign="middle",
        )
        self.add_widget(self._label)
        self.bind(pos=self._sync_canvas, size=self._sync_canvas)
        self.hide()

    def _sync_canvas(self, *_):
        self._shade_rect.pos = self.pos
        self._shade_rect.size = self.size
        self._label.pos = self.pos
        self._label.size = self.size
        self._label.text_size = self.size

    def show(self, seconds_left):
        self._active = True
        self.opacity = 1
        number = max(1, int(seconds_left))
        self._label.text = str(number)

    def hide(self):
        self._active = False
        self.opacity = 0
        self._label.text = ""

    def on_touch_down(self, touch):
        if not self._active:
            return False
        return True

    def on_touch_move(self, touch):
        if not self._active:
            return False
        return True

    def on_touch_up(self, touch):
        if not self._active:
            return False
        return True


class RoomScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        register_game_font()
        self.disabled = True

        self.room_code = ""
        self.room_state = {}
        self._poll_event = None
        self._voice_ui_event = None
        self._last_voice_ping_ts = 0.0
        self.voice_engine = RoomVoiceEngine()

        root = ScreenBackground()
        content = BoxLayout(
            orientation="vertical",
            padding=[dp(14), dp(18), dp(14), dp(14)],
            spacing=dp(8),
        )

        top_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(54))
        self.back_btn = AppButton(text="В меню", compact=True, size_hint=(None, None), size=(dp(132), dp(50)))
        self.back_btn.bind(on_release=self._go_back_to_menu)
        top_row.add_widget(self.back_btn)
        top_row.add_widget(Widget())
        self.refresh_btn = AppButton(text="Обновить", compact=True, size_hint=(None, None), size=(dp(132), dp(50)))
        self.refresh_btn.bind(on_release=lambda *_: self._poll_state())
        top_row.add_widget(self.refresh_btn)
        content.add_widget(top_row)

        content.add_widget(BrandTitle(text="ALIAS ONLINE", height=dp(88), font_size=sp(38), shadow_step=dp(3)))
        self.scores_label = BodyLabel(center=True, color=COLORS["accent"], font_size=sp(28), size_hint_y=None, text="")
        content.add_widget(self.scores_label)
        content.add_widget(PixelLabel(text="Комната", center=True, font_size=sp(24), size_hint_y=None))
        self.room_meta_label = BodyLabel(center=True, color=COLORS["text_muted"], font_size=sp(12), size_hint_y=None, text="")
        content.add_widget(self.room_meta_label)
        self.role_label = BodyLabel(center=True, color=COLORS["accent"], font_size=sp(13), size_hint_y=None, text="")
        content.add_widget(self.role_label)
        self.phase_label = BodyLabel(center=True, color=COLORS["warning"], font_size=sp(12), size_hint_y=None, text="")
        content.add_widget(self.phase_label)
        self.players_label = BodyLabel(center=True, color=COLORS["text_muted"], font_size=sp(11), size_hint_y=None, text="")
        content.add_widget(self.players_label)

        word_card = RoundedPanel(
            orientation="vertical",
            size_hint_y=None,
            height=dp(160),
            spacing=dp(6),
            padding=[dp(14), dp(10), dp(14), dp(10)],
        )
        word_card.add_widget(PixelLabel(text="Слово для объяснения", center=True, font_size=sp(13), size_hint_y=None))
        self.word_label = PixelLabel(text="...", center=True, font_size=sp(28), size_hint_y=None, color=COLORS["accent"])
        word_card.add_widget(self.word_label)

        action_row = BoxLayout(orientation="horizontal", spacing=dp(10), size_hint_y=None, height=dp(48))
        self.start_game_btn = AppButton(text="Начать игру", compact=True, font_size=sp(13))
        self.start_game_btn.bind(on_release=self._start_game)
        action_row.add_widget(self.start_game_btn)
        self.skip_word_btn = AppButton(text="Скип слова (-1)", compact=True, font_size=sp(13))
        self.skip_word_btn.bind(on_release=self._skip_word)
        action_row.add_widget(self.skip_word_btn)
        word_card.add_widget(action_row)
        content.add_widget(word_card)

        voice_card = RoundedPanel(
            orientation="vertical",
            size_hint_y=None,
            height=dp(156),
            spacing=dp(6),
            padding=[dp(14), dp(10), dp(14), dp(10)],
        )
        voice_card.add_widget(PixelLabel(text="Голосовой чат в игре", center=True, font_size=sp(13), size_hint_y=None))

        mic_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(78))
        mic_row.add_widget(Widget())
        self.mic_button = VoiceMicButton()
        self.mic_button.bind(on_release=self._toggle_mic)
        mic_row.add_widget(self.mic_button)
        mic_row.add_widget(Widget())
        voice_card.add_widget(mic_row)

        self.voice_status = BodyLabel(
            center=True,
            color=COLORS["text_muted"],
            font_size=sp(11),
            size_hint_y=None,
            text="Нажми на микрофон: зелёный = говоришь, зачеркнутый = выключен.",
        )
        voice_card.add_widget(self.voice_status)
        content.add_widget(voice_card)

        chat_card = RoundedPanel(
            orientation="vertical",
            size_hint_y=1,
            spacing=dp(8),
            padding=[dp(14), dp(12), dp(14), dp(12)],
        )
        chat_card.add_widget(PixelLabel(text="Текстовый чат", center=True, font_size=sp(13), size_hint_y=None))

        self.chat_scroll = ScrollView(do_scroll_x=False, bar_width=dp(4), scroll_type=["bars", "content"])
        self.chat_box = BoxLayout(orientation="vertical", spacing=dp(6), size_hint_y=None)
        self.chat_box.bind(minimum_height=self.chat_box.setter("height"))
        self.chat_scroll.add_widget(self.chat_box)
        chat_card.add_widget(self.chat_scroll)

        self.chat_input_row = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(48))
        self.chat_input = AppTextInput(hint_text="Пиши догадку в чат...", height=dp(46))
        self.chat_input_row.add_widget(self.chat_input)
        self.send_btn = AppButton(text="Отправить", compact=True, font_size=sp(13), size_hint=(None, None), size=(dp(130), dp(46)))
        self.send_btn.bind(on_release=self._send_chat_message)
        self.chat_input_row.add_widget(self.send_btn)
        chat_card.add_widget(self.chat_input_row)

        self.status_label = BodyLabel(
            center=True,
            color=COLORS["text_muted"],
            font_size=sp(11),
            size_hint_y=None,
            text="Ведущий запускает игру, затем объясняет слова голосом.",
        )
        chat_card.add_widget(self.status_label)
        content.add_widget(chat_card)

        self.countdown_overlay = FullscreenCountdownOverlay()

        root.add_widget(content)
        root.add_widget(self.countdown_overlay)
        self.add_widget(root)

    def on_pre_enter(self, *_):
        self.disabled = False
        app = App.get_running_app()
        room_data = app.get_active_room() if app is not None else {}
        self.room_code = (room_data or {}).get("code", "")
        self._last_voice_ping_ts = 0.0
        self.mic_button.set_muted(True)
        self.mic_button.set_level(0.0)
        self.countdown_overlay.hide()
        self._start_polling()
        self._start_voice_ui_sync()
        self._start_voice_engine()
        self._poll_state()

    def on_leave(self, *_):
        self._stop_polling()
        self._stop_voice_ui_sync()
        self._stop_voice_engine()
        self.countdown_overlay.hide()
        self.disabled = True

    def _go_back_to_menu(self, *_):
        self.manager.current = "start"

    def _player_name(self):
        app = App.get_running_app()
        return app.resolve_player_name() if app is not None else None

    def _current_phase(self):
        phase = (self.room_state.get("game_phase") or "").strip().lower()
        if phase in {"lobby", "countdown", "round"}:
            return phase
        room_phase = (self.room_state.get("room", {}).get("game_phase") or "").strip().lower()
        if room_phase in {"lobby", "countdown", "round"}:
            return room_phase
        return "lobby"

    def _is_explainer(self):
        room = self.room_state.get("room", {})
        return bool(self._player_name() and self._player_name() == room.get("current_explainer"))

    def _start_polling(self):
        self._stop_polling()
        self._poll_event = Clock.schedule_interval(lambda _dt: self._poll_state(), 1.0)

    def _stop_polling(self):
        if self._poll_event is not None:
            self._poll_event.cancel()
            self._poll_event = None

    def _start_voice_ui_sync(self):
        self._stop_voice_ui_sync()
        self._voice_ui_event = Clock.schedule_interval(lambda _dt: self._sync_voice_ui(), 0.12)

    def _stop_voice_ui_sync(self):
        if self._voice_ui_event is not None:
            self._voice_ui_event.cancel()
            self._voice_ui_event = None

    def _start_voice_engine(self):
        player_name = self._player_name()
        if not self.voice_engine.available or not player_name or not self.room_code:
            return

        self.voice_engine.start(
            room_code=self.room_code,
            player_name=player_name,
            should_transmit=lambda: self._is_explainer() and self._current_phase() == "round" and not self.mic_button.muted,
        )
        self.voice_engine.set_muted(self.mic_button.muted)

    def _stop_voice_engine(self):
        self.voice_engine.stop()

    def _set_button_visibility(self, button, visible):
        button.disabled = not visible
        button.opacity = 1 if visible else 0

    def _show_explainer_controls(self, is_explainer, phase):
        self._set_button_visibility(self.start_game_btn, is_explainer and phase == "lobby")
        self._set_button_visibility(self.skip_word_btn, is_explainer and phase == "round")

    def _set_chat_input_visibility(self, visible):
        row_height = dp(48) if visible else dp(0)
        self.chat_input_row.height = row_height
        self.chat_input_row.opacity = 1 if visible else 0
        self.chat_input_row.disabled = not visible
        self.chat_input.disabled = not visible
        self.send_btn.disabled = not visible

    def _poll_state(self):
        if not self.room_code:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Комната не выбрана. Создай комнату или зайди в существующую."
            return

        player_name = self._player_name()
        if not player_name:
            self.status_label.color = COLORS["error"]
            self.status_label.text = "Сессия не найдена. Войди в аккаунт заново."
            return

        try:
            state = get_online_room_state(room_code=self.room_code, player_name=player_name)
        except ConnectionError as error:
            self.status_label.color = COLORS["error"]
            self.status_label.text = str(error)
            return
        except ValueError as error:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = str(error)
            return

        self.room_state = state
        app = App.get_running_app()
        if app is not None:
            app.set_active_room(state.get("room", {}))
        self._apply_state()

    def _apply_state(self):
        room = self.room_state.get("room", {})
        players = self.room_state.get("players", [])
        scores = self.room_state.get("scores", [])
        messages = self.room_state.get("messages", [])

        player_name = self._player_name() or ""
        is_explainer = player_name == room.get("current_explainer")
        phase = self._current_phase()
        countdown_left = int(self.room_state.get("countdown_left_sec") or 0)
        round_left = int(self.room_state.get("round_left_sec") or 0)

        room_name = room.get("room_name", "Комната")
        code = room.get("code", self.room_code)
        players_text = f"{room.get('players_count', '?')}/{room.get('max_players', '?')}"
        self.room_meta_label.text = f"{room_name} | Код: {code} | Игроков: {players_text}"

        if is_explainer:
            self.role_label.text = "Роль: ведущий (объясняешь слова)"
            self.word_label.text = self.room_state.get("current_word") or "..."
            self.chat_input.hint_text = "Ведущий не пишет в чат."
            self._set_chat_input_visibility(False)
            self.mic_button.set_enabled(True)
        else:
            self.role_label.text = "Роль: угадываешь (пиши слово в чат)"
            self.word_label.text = "Слово скрыто"
            self.chat_input.hint_text = "Пиши догадку в чат..."
            self._set_chat_input_visibility(True)
            self.mic_button.set_enabled(False)
            self.mic_button.set_muted(True)
            self.voice_engine.set_muted(True)

        if phase == "lobby":
            self.phase_label.color = COLORS["warning"]
            self.phase_label.text = "Лобби: ведущий может начать игру"
            self.countdown_overlay.hide()
        elif phase == "countdown":
            self.phase_label.color = COLORS["accent"]
            self.phase_label.text = f"Игра начнется через {countdown_left} сек"
            if countdown_left > 0:
                self.countdown_overlay.show(countdown_left)
            else:
                self.countdown_overlay.show(1)
        else:
            self.phase_label.color = COLORS["success"]
            self.phase_label.text = f"Раунд: осталось {round_left} сек"
            self.countdown_overlay.hide()

        self._show_explainer_controls(is_explainer, phase)

        if players:
            self.players_label.text = "Игроки: " + ", ".join(players)
        else:
            self.players_label.text = "Игроки: пока нет данных"

        if scores:
            score_text = "   ".join(f"{x.get('player_name')}: {x.get('score')}" for x in scores)
            self.scores_label.text = f"СЧЕТ  {score_text}"
        else:
            self.scores_label.text = "СЧЕТ  0"

        voice_active = bool(self.room_state.get("voice_active"))
        voice_speaker = self.room_state.get("voice_speaker")
        if not self.voice_engine.available:
            self.voice_status.color = COLORS["warning"]
            self.voice_status.text = "Голос неактивен: установи sounddevice + numpy."
        elif phase != "round":
            self.voice_status.color = COLORS["text_muted"]
            self.voice_status.text = "Голосовой чат станет активным после старта раунда."
        elif voice_active and voice_speaker:
            self.voice_status.color = COLORS["success"]
            self.voice_status.text = f"Сейчас говорит: {voice_speaker}"
        else:
            self.voice_status.color = COLORS["text_muted"]
            self.voice_status.text = "Сейчас никто не говорит."

        self._render_messages(messages)

    def _render_messages(self, messages):
        self.chat_box.clear_widgets()

        if not messages:
            self.chat_box.add_widget(
                BodyLabel(
                    center=True,
                    color=COLORS["text_muted"],
                    font_size=sp(11),
                    text="Чат пуст. Напиши первое сообщение.",
                    size_hint_y=None,
                )
            )
            return

        for message in messages[-50:]:
            message_type = message.get("message_type", "chat")
            sender = message.get("player_name", "")
            text = message.get("message", "")

            if message_type == "system":
                line = f"[Система] {text}"
                color = COLORS["warning"]
            elif message_type == "guess":
                line = f"{sender}: {text}"
                color = COLORS["text_soft"]
            else:
                line = f"{sender}: {text}"
                color = COLORS["text"]

            self.chat_box.add_widget(
                BodyLabel(
                    text=line,
                    color=color,
                    font_size=sp(12),
                    size_hint_y=None,
                )
            )

        Clock.schedule_once(lambda *_: setattr(self.chat_scroll, "scroll_y", 0), 0)

    def _start_game(self, *_):
        if not self._is_explainer():
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Начать игру может только ведущий."
            return

        if self._current_phase() != "lobby":
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Игра уже запущена."
            return

        player_name = self._player_name()
        try:
            start_room_game(room_code=self.room_code, player_name=player_name)
        except ConnectionError as error:
            self.status_label.color = COLORS["error"]
            self.status_label.text = str(error)
            return
        except ValueError as error:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = str(error)
            return

        self.status_label.color = COLORS["success"]
        self.status_label.text = "Старт игры! На экране общий отсчет 10 секунд."
        self._poll_state()

    def _send_chat_message(self, *_):
        if self._is_explainer():
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Ведущий не может писать в чат. Только объяснять голосом."
            return

        text = self.chat_input.text.strip()
        if not text:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Введи текст сообщения."
            return

        player_name = self._player_name()
        if not player_name:
            self.status_label.color = COLORS["error"]
            self.status_label.text = "Сессия игрока не найдена."
            return

        phase = self._current_phase()
        try:
            if phase != "round":
                self.status_label.color = COLORS["warning"]
                self.status_label.text = "Раунд еще не начался."
                return
            result = send_room_guess(room_code=self.room_code, player_name=player_name, guess=text)
            if result.get("correct"):
                awarded_player = result.get("awarded_player") or "ведущий"
                guesser_player = result.get("guesser_player") or player_name
                self.status_label.color = COLORS["success"]
                self.status_label.text = f"Верно! {awarded_player} +1 и {guesser_player} +1."
            else:
                self.status_label.color = COLORS["text_muted"]
                self.status_label.text = "Догадка отправлена."
        except ConnectionError as error:
            self.status_label.color = COLORS["error"]
            self.status_label.text = str(error)
            return
        except ValueError as error:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = str(error)
            return

        self.chat_input.text = ""
        self._poll_state()

    def _skip_word(self, *_):
        if not self._is_explainer():
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Скипать слова может только ведущий."
            return
        if self._current_phase() != "round":
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Скип доступен только во время раунда."
            return

        player_name = self._player_name()
        try:
            response = skip_room_word(room_code=self.room_code, player_name=player_name)
        except ConnectionError as error:
            self.status_label.color = COLORS["error"]
            self.status_label.text = str(error)
            return
        except ValueError as error:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = str(error)
            return

        self.status_label.color = COLORS["warning"]
        self.status_label.text = f"Слово скипнуто. Штраф {response.get('delta', -1)}."
        self._poll_state()

    def _toggle_mic(self, *_):
        if not self._is_explainer():
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Микрофон активен только у ведущего."
            return

        new_muted = not self.mic_button.muted
        self.mic_button.set_muted(new_muted)
        self.voice_engine.set_muted(new_muted)
        if new_muted:
            self.status_label.color = COLORS["text_muted"]
            self.status_label.text = "Микрофон выключен."
        else:
            self.status_label.color = COLORS["success"]
            self.status_label.text = "Микрофон включен."

    def _sync_voice_ui(self):
        if not self.voice_engine.available:
            self.mic_button.set_level(0.0)
            return

        level = self.voice_engine.level() if self.voice_engine.active() else 0.0
        if self.mic_button.muted:
            level = 0.0
        self.mic_button.set_level(level)

        if not self._is_explainer() or self.mic_button.muted or self._current_phase() != "round":
            return

        if level < 0.06:
            return

        now_ts = time.time()
        if now_ts - self._last_voice_ping_ts < 0.7:
            return

        self._last_voice_ping_ts = now_ts
        player_name = self._player_name()
        if not player_name:
            return

        try:
            ping_room_voice(room_code=self.room_code, player_name=player_name, active_seconds=3)
        except (ConnectionError, ValueError):
            pass
