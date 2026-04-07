import logging
import time

from kivy.app import App

logger = logging.getLogger(__name__)
from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from services import RoomVoiceEngine
from controllers import RoomGameController, RoomPollingController

# Import safe voice polling controller
try:
    from controllers.voice_polling_controller_safe import VoicePollingController
    logger.info("Loaded VoicePollingController from voice_polling_controller_safe")
except ImportError:
    logger.warning("Could not import voice_polling_controller_safe, falling back to regular")
    from controllers import VoicePollingController
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
    TouchPassthroughFloatLayout,
    register_game_font,
)
from screens.room.widgets import (
    ExplainerSpotlightCard,
    FullscreenCountdownOverlay,
    ScoreBadge,
    SwipeWordCard,
    VoiceMicButton,
)
from screens.room.state_mixin import RoomStateMixin
from screens.room.voice_mixin import RoomVoiceMixin
from screens.room.chat_mixin import RoomChatMixin
from screens.room.layout_mixin import RoomLayoutMixin


class RoomScreen(RoomStateMixin, RoomVoiceMixin, RoomChatMixin, RoomLayoutMixin, Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        register_game_font()
        self.disabled = True

        self.room_code = ""
        self.room_state = {}
        self._room_state_version = ""
        self._poll_event = None
        self._voice_ui_event = None
        self._last_voice_ping_ts = 0.0
        self._smoothed_voice_level = 0.0
        self._last_chat_signature = None
        self._leave_sent = False
        self.leave_confirm_popup = None
        self.voice_engine = RoomVoiceEngine()
        self._mic_muted_state = True
        self._start_game_scheduled = False
        self._last_start_attempt_ts = 0.0
        self._start_game_request_in_flight = False
        self._start_game_request_token = 0
        self._start_game_watchdog_event = None
        self._rejoin_request_token = 0
        self._rejoin_in_flight = False
        self._rejoin_recover_attempts = 0
        self._local_starts_count = 0
        self._last_players_signature = None
        self._last_chat_mount_signature = None
        self._last_progress_signature = None
        self._last_overlay_geometry_signature = None
        self._profile_cache = {}
        self._profile_cache_ts = 0.0
        self._poll_in_flight = False
        self._poll_token = 0
        self._poll_started_at = 0.0
        self._chat_request_in_flight = False
        self._skip_request_in_flight = False
        self._chat_request_token = 0
        self._skip_request_token = 0
        self._countdown_event = None
        self._countdown_end_time = 0.0
        self._countdown_start_local_time = 0.0
        self._round_timer_event = None
        self._round_end_time = 0.0
        self._round_start_local_time = 0.0
        self._message_history = []
        self._last_message_id = 0

        self.game_controller = RoomGameController(self)
        self.polling_controller = RoomPollingController(self)
        self.voice_polling_controller = VoicePollingController(self.voice_engine)

        self.COLORS = COLORS

        root = ScreenBackground(variant="game")
        content = BoxLayout(
            orientation="vertical",
            padding=[dp(8), dp(10), dp(8), dp(10)],
            spacing=dp(6),
            size_hint_y=None,
        )
        self._content_box = content
        content.bind(minimum_height=content.setter("height"))

        top_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(56))
        self.back_btn = AppButton(text="В меню", compact=True, size_hint=(None, None), size=(dp(122), dp(46)))
        self.back_btn.bind(on_release=self._go_back_to_menu)
        self._set_room_exit_button(False)
        top_row.add_widget(self.back_btn)
        top_row.add_widget(Widget())
        self.coin_badge = CoinBadge(size=(dp(116), dp(46)))
        top_row.add_widget(self.coin_badge)
        content.add_widget(top_row)

        self.room_meta_wrap_height = dp(18)
        self.room_meta_wrap = BoxLayout(orientation="horizontal", size_hint_y=None, height=self.room_meta_wrap_height)
        self.room_meta_label = BodyLabel(center=True, color=COLORS["text_muted"], font_size=sp(11), size_hint_y=None, text="")
        self.room_meta_wrap.add_widget(self.room_meta_label)
        content.add_widget(self.room_meta_wrap)
        self.brand_title_height = dp(72)
        self.brand_title = BrandTitle(
            text="ALIAS ONLINE",
            height=self.brand_title_height,
            font_size=sp(38),
            shadow_step=dp(3),
        )
        content.add_widget(self.brand_title)

        self.explainer_status_label = BodyLabel(
            center=True,
            color=COLORS["accent"],
            font_size=sp(12),
            size_hint_y=None,
            text="Объясняет слова: -- | Микрофон: --",
        )
        content.add_widget(self.explainer_status_label)

        self.players_wrap_height = dp(248)
        self.players_wrap_round_height = dp(176)
        self.players_wrap = RoundedPanel(
            orientation="vertical",
            spacing=dp(6),
            padding=[dp(10), dp(8), dp(10), dp(8)],
            size_hint_y=None,
            height=self.players_wrap_height,
        )
        self.players_wrap_title = PixelLabel(text="Игроки в комнате • 0/0", center=True, font_size=sp(13), size_hint_y=None)
        self.players_wrap.add_widget(self.players_wrap_title)
        self.players_scroll = ScrollView(do_scroll_x=False, bar_width=dp(4), scroll_type=["bars", "content"])
        self.players_box = GridLayout(
            cols=3,
            spacing=dp(8),
            padding=[dp(4), dp(4), dp(4), dp(4)],
            size_hint=(None, None),
            row_default_height=dp(126),
            row_force_default=True,
            col_default_width=dp(108),
            col_force_default=True,
        )
        self.players_box.bind(minimum_height=self.players_box.setter("height"))
        self.players_scroll.bind(width=self._sync_players_grid_width)
        self.players_scroll.add_widget(self.players_box)
        self.players_wrap.add_widget(self.players_scroll)
        content.add_widget(self.players_wrap)

        self.scores_wrap_height = dp(132)
        self.scores_wrap_overlay_height = dp(162)
        self.scores_wrap = FloatLayout(size_hint_y=None, height=self.scores_wrap_height)
        self.score_chat_layer = TouchPassthroughFloatLayout(size_hint=(1, 1), opacity=0, disabled=True)
        self.scores_wrap.add_widget(self.score_chat_layer)
        self.score_badge = ScoreBadge(pos_hint={"center_x": 0.5, "top": 1.0})
        self.scores_wrap.add_widget(self.score_badge)
        self.mic_button_top = VoiceMicButton(size=(dp(88), dp(88)), pos_hint={"right": 0.98, "top": 0.96})
        self.mic_button_top.bind(on_release=self._toggle_mic)
        self.mic_button_top.opacity = 0
        self.mic_button_top.disabled = True
        self.scores_wrap.add_widget(self.mic_button_top)
        content.add_widget(self.scores_wrap)

        self.players_summary_wrap_height = dp(22)
        self.players_summary_wrap = BoxLayout(orientation="horizontal", size_hint_y=None, height=self.players_summary_wrap_height)
        self.players_label = BodyLabel(center=True, color=COLORS["text_muted"], font_size=sp(11), size_hint_y=None, text="")
        self.players_summary_wrap.add_widget(self.players_label)
        content.add_widget(self.players_summary_wrap)

        self.lobby_start_height = dp(52)
        self.lobby_action_bar = TouchPassthroughFloatLayout(
            size_hint=(1, None),
            height=dp(0),
            opacity=0,
            pos_hint={"x": 0, "y": 0},
        )
        self.lobby_start_row = AnchorLayout(size_hint=(1, 1), anchor_x="center", anchor_y="center")
        self.start_game_btn = AppButton(
            text="Начать игру",
            compact=True,
            font_size=sp(14),
            size_hint=(None, None),
            size=(dp(228), dp(46)),
        )
        self.start_game_btn.bind(on_release=lambda *_: self.game_controller.queue_start_game())
        self.lobby_start_row.add_widget(self.start_game_btn)
        self.wait_host_btn = AppButton(
            text="Ожидание старта от хоста",
            compact=True,
            font_size=sp(13),
            size_hint=(None, None),
            size=(dp(228), dp(46)),
        )
        self.wait_host_btn.disabled = True
        self.wait_host_btn.opacity = 0
        self.lobby_start_row.add_widget(self.wait_host_btn)
        self.lobby_action_bar.add_widget(self.lobby_start_row)

        self.phase_wrap_height = dp(62)
        self.phase_wrap = RoundedPanel(
            orientation="horizontal",
            size_hint_y=None,
            height=self.phase_wrap_height,
            padding=[dp(12), dp(8), dp(12), dp(8)],
            bg_color=(0.08, 0.13, 0.21, 0.94),
            shadow_alpha=0.16,
        )
        self.phase_wrap._border_color.rgba = COLORS["accent"]
        self.phase_wrap._border_line.width = 1.5
        self.phase_label = PixelLabel(center=True, color=COLORS["warning"], font_size=sp(23), size_hint_y=None, text="")
        self.phase_wrap.add_widget(self.phase_label)
        content.add_widget(self.phase_wrap)

        self.explainer_card_height = dp(138)
        self.explainer_card = ExplainerSpotlightCard()
        self.explainer_card.height = self.explainer_card_height
        content.add_widget(self.explainer_card)

        self.word_push_spacer = Widget(size_hint_y=None, height=dp(0))
        content.add_widget(self.word_push_spacer)

        self.word_card_height = dp(188)
        self.word_stage_height = dp(198)
        self.word_stage = FloatLayout(size_hint_y=None, height=self.word_stage_height)
        self.word_stage.bind(size=self._sync_word_stage_layout, pos=self._sync_word_stage_layout)
        self.word_card = SwipeWordCard(
            swipe_callback=self._handle_word_swipe,
            orientation="vertical",
            size_hint=(None, None),
            height=self.word_card_height,
            spacing=dp(0),
            padding=[dp(16), dp(8), dp(16), dp(8)],
            bg_color=(1.0, 0.95, 0.36, 0.98),
            shadow_alpha=0.16,
        )
        self.word_card._border_color.rgba = COLORS["button"]
        self.word_card._border_line.width = 2.2
        self.word_label = Label(
            text="...",
            font_name="GameFont",
            font_size=sp(56),
            color=(0.05, 0.09, 0.15, 1),
            halign="center",
            valign="middle",
        )
        self.word_label.bind(size=self._sync_word_label)
        self.word_card.add_widget(self.word_label)
        self.word_stage.add_widget(self.word_card)
        content.add_widget(self.word_stage)

        self.voice_card_height = dp(0)
        self.voice_card = RoundedPanel(
            orientation="horizontal",
            size_hint_y=None,
            height=self.voice_card_height,
            spacing=dp(10),
            padding=[dp(4), dp(0), dp(4), dp(0)],
            bg_color=(0, 0, 0, 0),
            shadow_alpha=0,
        )
        voice_text_col = BoxLayout(orientation="vertical", spacing=dp(0))
        voice_text_col.add_widget(PixelLabel(text="Микрофон", font_size=sp(11), size_hint_y=None))
        self.voice_status = BodyLabel(text="Выключен", color=COLORS["text_muted"], font_size=sp(10.5), size_hint_y=None)
        voice_text_col.add_widget(self.voice_status)
        self.voice_card.add_widget(voice_text_col)
        self.voice_card.add_widget(Widget())
        self.mic_button = VoiceMicButton()
        self.mic_button.bind(on_release=self._toggle_mic)
        self.voice_card.add_widget(self.mic_button)
        content.add_widget(self.voice_card)

        self.chat_host = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(210))

        self.chat_card = RoundedPanel(
            orientation="vertical",
            size_hint_y=1,
            spacing=dp(6),
            padding=[dp(12), dp(8), dp(12), dp(8)],
        )
        self.chat_title = PixelLabel(text="Текстовый чат", center=True, font_size=sp(13), size_hint_y=None)
        self.chat_card.add_widget(self.chat_title)

        self.chat_scroll = ScrollView(do_scroll_x=False, bar_width=dp(4), scroll_type=["bars", "content"])
        self.chat_box = BoxLayout(orientation="vertical", spacing=dp(2), size_hint_y=None)
        self.chat_box.bind(minimum_height=self.chat_box.setter("height"))
        self.chat_scroll.add_widget(self.chat_box)
        self.chat_card.add_widget(self.chat_scroll)

        self.chat_input_row = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(48))
        self.chat_input = AppTextInput(hint_text="Пиши догадку в чат...", height=dp(46))
        self.chat_input_row.add_widget(self.chat_input)
        self.send_btn = AppButton(text="Отправить", compact=True, font_size=sp(13), size_hint=(None, None), size=(dp(130), dp(46)))
        self.send_btn.bind(on_release=self._send_chat_message)
        self.chat_input_row.add_widget(self.send_btn)
        self.chat_card.add_widget(self.chat_input_row)

        self.status_label = BodyLabel(
            center=True,
            color=COLORS["text_muted"],
            font_size=sp(11),
            size_hint_y=None,
            auto_height=False,
            text="Объясняющий запускает игру, затем объясняет слова голосом.",
        )
        self.status_label.height = dp(0)
        self.status_label.opacity = 0
        self.status_label.disabled = True
        self.chat_card.add_widget(self.status_label)
        self.chat_host.add_widget(self.chat_card)
        content.add_widget(self.chat_host)

        self.countdown_overlay = FullscreenCountdownOverlay()
        self.chat_overlay_layer = FloatLayout(size_hint=(None, None), size=(0, 0), opacity=0, disabled=True)

        self._content_scroll = ScrollView(do_scroll_x=False, bar_width=dp(4), scroll_type=["bars", "content"])
        self._content_scroll.add_widget(content)
        root.add_widget(self._content_scroll)
        root.add_widget(self.lobby_action_bar)
        root.add_widget(self.chat_overlay_layer)
        root.add_widget(self.countdown_overlay)
        self.loading_overlay = LoadingOverlay()
        root.add_widget(self.loading_overlay)
        self.add_widget(root)

    def on_pre_enter(self, *_):
        logger.debug("Entering room screen")
        self.disabled = False
        app = App.get_running_app()
        room_data = app.get_active_room() if app is not None else {}
        self.room_code = (room_data or {}).get("code", "")
        self.room_state = {}
        logger.debug(f"Room code: {self.room_code}")
        player_name = self._player_name()
        self._last_voice_ping_ts = 0.0
        self._smoothed_voice_level = 0.0
        self._last_chat_signature = None
        self._last_players_signature = None
        self._last_chat_mount_signature = None
        self._last_progress_signature = None
        self._last_overlay_geometry_signature = None
        self._leave_sent = False
        self._profile_cache = {}
        self._profile_cache_ts = 0.0
        self._chat_request_in_flight = False
        self._skip_request_in_flight = False
        self._chat_request_token = 0
        self._skip_request_token = 0
        self._message_history = []
        self._last_message_id = 0

        self.game_controller.reset_for_new_room()
        self.polling_controller.reset_for_new_room()
        self.voice_polling_controller.reset_for_new_room()

        self._reset_transient_layers()
        self._set_mic_muted(True)
        self._set_mic_level(0.0)
        self.coin_badge.refresh_from_session()
        self.status_label.color = COLORS["text_muted"]
        self.status_label.text = "Синхронизируем комнату..."

        cached_server_state = room_data.get("_server_state") if isinstance(room_data, dict) else None
        if isinstance(cached_server_state, dict) and cached_server_state.get("viewer"):
            initial_state = dict(cached_server_state)
            initial_messages = initial_state.get("messages", [])
            if isinstance(initial_messages, list):
                initial_state["messages"] = self._merge_message_history(initial_messages, since_id=0)
                if initial_messages:
                    try:
                        self._last_message_id = int(initial_messages[-1].get("id") or 0)
                    except (TypeError, ValueError):
                        self._last_message_id = 0
            room_info = initial_state.get("room", {})
            if isinstance(room_info, dict):
                self._room_state_version = (room_info.get("updated_at") or "")
            logger.debug(f"Loaded cached state. Phase: {initial_state.get('game_phase', '?')}, Version: {self._room_state_version}")
            self.room_state = initial_state
            self.status_label.color = COLORS["text_muted"]
            self.status_label.text = ""
            if app is not None:
                app.set_active_room(initial_state.get("room", room_data))
        else:
            logger.debug("No cached state available")

        logger.debug("[RoomScreen.on_pre_enter] Starting state polling")
        try:
            self.polling_controller.start_polling()
            logger.debug("[RoomScreen.on_pre_enter] State polling started")
        except Exception as e:
            logger.error("[RoomScreen.on_pre_enter] State polling FAILED", exc_info=True)

        logger.debug("[RoomScreen.on_pre_enter] Starting voice UI sync")
        try:
            self._start_voice_ui_sync()
            logger.debug("[RoomScreen.on_pre_enter] Voice UI sync started")
        except Exception as e:
            logger.error("[RoomScreen.on_pre_enter] Voice UI sync FAILED", exc_info=True)

        logger.debug("[RoomScreen.on_pre_enter] Starting voice engine")
        try:
            self._start_voice_engine()
            logger.debug("[RoomScreen.on_pre_enter] Voice engine started")
        except Exception as e:
            logger.error("[RoomScreen.on_pre_enter] Voice engine FAILED", exc_info=True)

        logger.debug("[RoomScreen.on_pre_enter] [CRITICAL] Checking if initial poll needed")
        if not self.room_state.get("viewer"):
            logger.debug("[RoomScreen.on_pre_enter] [CRITICAL] Initial poll state needed")
            self.polling_controller._poll_state()

        logger.debug("[RoomScreen.on_pre_enter] [CRITICAL] Applying state - THIS MAY HANG IF BUG")
        try:
            self._apply_state()
            logger.debug("[RoomScreen.on_pre_enter] [CRITICAL] State applied successfully")
        except Exception as e:
            logger.error("[RoomScreen.on_pre_enter] [CRITICAL] Apply state FAILED", exc_info=True)
            raise

        logger.debug("[RoomScreen.on_pre_enter] [CRITICAL] Ensuring interaction ready")
        try:
            self._ensure_interaction_ready()
            logger.info("[RoomScreen.on_pre_enter] [CRITICAL] COMPLETED SUCCESSFULLY - VOICE POLLING DEFERRED TO on_enter()")
        except Exception as e:
            logger.error("[RoomScreen.on_pre_enter] [CRITICAL] Ensure interaction FAILED", exc_info=True)
            raise

    def on_enter(self):
        """Called when screen is fully visible and ready. Start voice polling here."""
        logger.info("[RoomScreen.on_enter] ===== ENTRY - Screen is now fully visible and initialized =====")
        try:
            # At this point, screen is fully ready, all widgets rendered, _apply_state completed
            player_name = self._player_name()
            client_id = self._client_id()

            logger.info(
                f"[RoomScreen.on_enter] Screen fully ready. "
                f"room_code={self.room_code}, player_name={player_name}"
            )

            if self.room_code and player_name:
                logger.info("[RoomScreen.on_enter] ===== STARTING VOICE POLLING NOW (screen ready) =====")
                try:
                    # Enable polling callbacks to execute
                    self.voice_polling_controller._is_polling_active = True
                    logger.debug("[RoomScreen.on_enter] Marked polling as active")

                    self.voice_polling_controller.start_polling(
                        room_code=self.room_code,
                        player_name=player_name,
                        client_id=client_id,
                    )
                    logger.info("[RoomScreen.on_enter] ===== VOICE POLLING STARTED SUCCESSFULLY =====")
                except Exception as e:
                    logger.error(
                        "[RoomScreen.on_enter] Voice polling FAILED",
                        exc_info=True
                    )
                    self.status_label.color = COLORS["warning"]
                    self.status_label.text = "Ошибка голосового чата. Игра продолжает работать."
            else:
                logger.warning(
                    f"[RoomScreen.on_enter] Cannot start polling: "
                    f"room_code={self.room_code}, player_name={player_name}"
                )

            logger.info("[RoomScreen.on_enter] ===== COMPLETED SUCCESSFULLY =====")
        except Exception as e:
            logger.error("[RoomScreen.on_enter] ===== CRASHED =====", exc_info=True)

    def on_leave(self, *_):
        logger.debug(f"Leaving room screen. Current phase: {self._current_phase()}")
        self.polling_controller.stop_polling()
        self.voice_polling_controller.stop_polling()
        self._stop_voice_ui_sync()
        self._stop_countdown_timer()
        self._stop_round_timer()
        self._stop_voice_engine()
        self.loading_overlay.hide()
        self.countdown_overlay.hide()
        self._dismiss_leave_popup()
        self._last_players_signature = None
        self._last_chat_mount_signature = None
        self._last_progress_signature = None
        self._last_overlay_geometry_signature = None
        self._chat_request_in_flight = False
        self._skip_request_in_flight = False
        self._chat_request_token += 1
        self._skip_request_token += 1
        self._message_history = []
        self._last_message_id = 0
        self._reset_transient_layers()
        self.disabled = True
