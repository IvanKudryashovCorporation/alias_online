import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from contextlib import suppress
from pathlib import Path

from kivy.app import App
from kivy.clock import Clock
from kivy.config import Config
from kivy.metrics import dp
from kivy.utils import platform

if platform in ("android", "ios"):
    Config.set("graphics", "fullscreen", "auto")
    Config.set("graphics", "borderless", "1")

try:
    from kivy.core.window import Window
except Exception:  # pragma: no cover - keep Android startup resilient
    Window = None
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import FadeTransition, Screen, ScreenManager
from services.profile_store import (
    apply_match_exit_penalty,
    get_active_profile,
    get_matchmaking_penalty,
    initialize_database,
    set_active_profile,
)
from services.room_hub import (
    is_local_room_server_url,
    leave_online_room,
    room_server_bind_params,
    room_server_url,
)
from ui.theme import register_game_font

if Window is not None:
    with suppress(Exception):
        Window.title = "Alias Online"
        Window.softinput_mode = "below_target"

if Window is not None and platform not in ("android", "ios"):
    with suppress(Exception):
        Window.size = (430, 820)

try:
    if platform == "android":
        from android.runnable import run_on_ui_thread
    else:
        def run_on_ui_thread(func):
            return func
except Exception:  # pragma: no cover
    def run_on_ui_thread(func):
        return func


class _SingleInstanceGuard:
    def __init__(self, name):
        self.name = name
        self._handle = None

    def acquire(self):
        if sys.platform != "win32":
            return True

        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(None, False, self.name)
        if not handle:
            return True

        self._handle = handle
        already_exists = kernel32.GetLastError() == 183
        return not already_exists

    def release(self):
        if self._handle is None or sys.platform != "win32":
            return

        import ctypes

        with suppress(Exception):
            ctypes.windll.kernel32.CloseHandle(self._handle)
        self._handle = None


def _runtime_log_path():
    app = App.get_running_app()
    user_data_dir = getattr(app, "user_data_dir", None) if app is not None else None
    if user_data_dir:
        return Path(user_data_dir) / "alias_runtime_error.log"
    return Path.home() / "alias_runtime_error.log"


def _log_unhandled_exception(exc_type, exc_value, exc_traceback):
    log_path = _runtime_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    error_dump = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    try:
        log_path.write_text(error_dump, encoding="utf-8")
    except OSError:
        pass
    sys.__excepthook__(exc_type, exc_value, exc_traceback)


sys.excepthook = _log_unhandled_exception


class AliasApp(App):
    guest_name = "Гость"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.authenticated = False
        self.guest_mode = False
        self.guest_counter = 0
        self.pending_registration_session_id = None
        self.active_room = {}
        self._room_server_process = None
        self._room_server_thread = None
        self._embedded_room_server = None
        self.guest_room_lock_until = 0.0
        self.guest_room_lock_reason = None

    def build(self):
        try:
            register_game_font()
            initialize_database()
            Clock.schedule_once(lambda *_: self._safe_start_room_server(), 0)
            Clock.schedule_once(lambda *_: self._refresh_mobile_window_mode(), 0)

            from screens.create_room import CreateRoomScreen
            from screens.email_verification_screen import EmailVerificationScreen
            from screens.entry_screen import EntryScreen
            from screens.friends import FriendsScreen
            from screens.join_room import JoinRoomScreen
            from screens.login_screen import LoginScreen
            from screens.password_recovery_screen import PasswordRecoveryScreen
            from screens.player_profile_screen import PlayerProfileScreen
            from screens.registration_screen import RegistrationScreen
            from screens.room_screen import RoomScreen
            from screens.rules import RulesScreen
            from screens.start_screen import StartScreen

            active_profile = get_active_profile()
            self.authenticated = active_profile is not None
            self.guest_mode = False

            screen_manager = ScreenManager(transition=FadeTransition(duration=0.18))
            screen_manager.add_widget(EntryScreen(name="entry"))
            screen_manager.add_widget(LoginScreen(name="login"))
            screen_manager.add_widget(RegistrationScreen(name="registration"))
            screen_manager.add_widget(PasswordRecoveryScreen(name="password_recovery"))
            screen_manager.add_widget(EmailVerificationScreen(name="email_verification"))
            screen_manager.add_widget(PlayerProfileScreen(name="player_profile"))
            screen_manager.add_widget(StartScreen(name="start"))
            screen_manager.add_widget(CreateRoomScreen(name="create_room"))
            screen_manager.add_widget(JoinRoomScreen(name="join_room"))
            screen_manager.add_widget(FriendsScreen(name="friends"))
            screen_manager.add_widget(RulesScreen(name="rules"))
            screen_manager.add_widget(RoomScreen(name="room"))
            screen_manager.bind(current=self._guard_session)
            screen_manager.current = "start" if self.authenticated else "entry"
            return screen_manager
        except Exception as error:
            _log_unhandled_exception(type(error), error, error.__traceback__)
            return self._build_startup_error_screen(error)

    def _safe_start_room_server(self):
        try:
            self._ensure_local_room_server()
        except Exception as error:
            _log_unhandled_exception(type(error), error, error.__traceback__)

    def _build_startup_error_screen(self, error):
        manager = ScreenManager(transition=FadeTransition(duration=0))
        screen = Screen(name="startup_error")
        content = BoxLayout(
            orientation="vertical",
            padding=[dp(18), dp(24), dp(18), dp(24)],
            spacing=dp(12),
        )
        content.add_widget(Label(text="ALIAS ONLINE", bold=True, font_size="24sp"))
        content.add_widget(
            Label(
                text="Ошибка запуска приложения.\nОткрой файл alias_runtime_error.log и пришли его.",
                halign="center",
                valign="middle",
            )
        )
        content.add_widget(
            Label(
                text=str(error),
                color=(1, 0.5, 0.5, 1),
                halign="center",
                valign="middle",
            )
        )
        screen.add_widget(content)
        manager.add_widget(screen)
        manager.current = "startup_error"
        return manager

    def _room_server_is_healthy(self, base_url=None):
        target_url = (base_url or room_server_url()).strip().rstrip("/")
        if not target_url:
            return False
        health_url = f"{target_url}/health"
        try:
            with urllib.request.urlopen(health_url, timeout=0.35) as response:
                return response.status == 200
        except (urllib.error.URLError, TimeoutError):
            return False

    def _ensure_local_room_server(self):
        configured_url = room_server_url(refresh=True)
        if not is_local_room_server_url(configured_url):
            return

        bind_host, bind_port = room_server_bind_params(configured_url)
        if self._room_server_is_healthy(configured_url):
            return

        root_dir = Path(__file__).resolve().parent
        if platform == "android":
            try:
                from server.room_server import create_server
            except Exception:
                self._embedded_room_server = None
                return

            db_path = Path(getattr(self, "user_data_dir", "") or (root_dir / "data")) / "room_server" / "rooms.db"
            try:
                self._embedded_room_server = create_server(host=bind_host, port=bind_port, db_path=db_path)
            except OSError:
                self._embedded_room_server = None
                return

            self._room_server_thread = threading.Thread(
                target=self._embedded_room_server.serve_forever,
                name="alias-room-server",
                daemon=True,
            )
            self._room_server_thread.start()
            return

        if platform == "ios":
            return

        server_script = root_dir / "server" / "room_server.py"
        if not server_script.exists():
            return

        creation_flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        try:
            self._room_server_process = subprocess.Popen(
                [sys.executable, str(server_script), "--host", bind_host, "--port", str(bind_port)],
                cwd=str(root_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
            )
        except OSError:
            self._room_server_process = None
            return

        return

    def on_stop(self):
        self._leave_active_room()
        process = self._room_server_process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1.2)
            except subprocess.TimeoutExpired:
                process.kill()

        embedded_server = self._embedded_room_server
        if embedded_server is not None:
            with suppress(Exception):
                embedded_server.shutdown()
            with suppress(Exception):
                embedded_server.server_close()
            self._embedded_room_server = None
            self._room_server_thread = None

    def has_session_access(self):
        return self.authenticated or self.guest_mode

    def current_profile(self):
        if not self.authenticated:
            return None
        return get_active_profile()

    def resolve_player_name(self):
        if self.guest_mode:
            return self.guest_name

        profile = self.current_profile()
        return profile.name if profile is not None else None

    def sign_in(self, profile=None):
        self.authenticated = profile is not None
        self.guest_mode = False
        self.clear_pending_registration_session()
        self.clear_active_room()

        if profile is not None:
            set_active_profile(profile.email)
        else:
            set_active_profile(None)

    def enter_guest_mode(self):
        self.authenticated = False
        self.guest_mode = True
        self.guest_counter += 1
        self.guest_name = f"Гость{self.guest_counter}"
        self.clear_pending_registration_session()
        self.clear_active_room()

    def start_registration_flow(self):
        self.authenticated = False
        self.guest_mode = False
        self.clear_pending_registration_session()
        set_active_profile(None)
        self.clear_active_room()

    def sign_out(self):
        self._leave_active_room()
        self.authenticated = False
        self.guest_mode = False
        self.clear_pending_registration_session()
        set_active_profile(None)
        self.clear_active_room()

    def set_pending_registration_session(self, session_id):
        clean_session_id = (session_id or "").strip()
        self.pending_registration_session_id = clean_session_id or None

    def clear_pending_registration_session(self):
        self.pending_registration_session_id = None

    def set_active_room(self, room):
        self.active_room = dict(room or {})

    def get_active_room(self):
        return dict(self.active_room or {})

    def clear_active_room(self):
        self.active_room = {}

    def room_access_state(self):
        if self.authenticated:
            profile = self.current_profile()
            if profile is not None:
                return get_matchmaking_penalty(profile.email)

        remaining_seconds = max(0, int(self.guest_room_lock_until - time.time()))
        return {
            "active": remaining_seconds > 0,
            "remaining_seconds": remaining_seconds,
            "blocked_until": None,
            "reason": self.guest_room_lock_reason if remaining_seconds > 0 else None,
        }

    def format_room_access_message(self, action_label="Действие"):
        state = self.room_access_state()
        if not state.get("active"):
            return ""

        remaining_seconds = max(0, int(state.get("remaining_seconds") or 0))
        minutes, seconds = divmod(remaining_seconds, 60)
        if minutes and seconds:
            eta = f"{minutes} мин {seconds} сек"
        elif minutes:
            eta = f"{minutes} мин"
        else:
            eta = f"{max(1, seconds)} сек"

        reason = (state.get("reason") or "Временное ограничение").strip()
        return (
            f"{action_label} сейчас недоступно.\n"
            f"Причина: {reason}.\n"
            f"Осталось подождать: {eta}."
        )

    def apply_room_exit_penalty(self, coin_penalty=50, cooldown_minutes=5):
        if self.authenticated:
            profile = self.current_profile()
            if profile is not None:
                return apply_match_exit_penalty(profile.email, coin_penalty=coin_penalty, cooldown_minutes=cooldown_minutes)

        self.guest_room_lock_until = max(self.guest_room_lock_until, time.time() + max(1, int(cooldown_minutes or 0)) * 60)
        self.guest_room_lock_reason = "Выход из игры"
        remaining_seconds = max(0, int(self.guest_room_lock_until - time.time()))
        return {
            "profile": None,
            "coins_deducted": 0,
            "remaining_coins": 0,
            "blocked_until": None,
            "remaining_seconds": remaining_seconds,
            "cooldown_minutes": max(1, int(cooldown_minutes or 0)),
            "reason": self.guest_room_lock_reason,
        }

    def _leave_active_room(self):
        room_code = (self.active_room or {}).get("code", "")
        player_name = self.resolve_player_name()
        if not room_code or not player_name:
            return

        try:
            leave_online_room(room_code=room_code, player_name=player_name)
        except (ConnectionError, ValueError):
            pass

    def _guard_session(self, manager, current_screen_name):
        if current_screen_name in {"entry", "login", "registration", "email_verification", "password_recovery"}:
            return

        if not self.has_session_access():
            manager.current = "entry"

    def on_start(self):
        self._refresh_mobile_window_mode()

    def on_resume(self):
        self._refresh_mobile_window_mode()
        return True

    def _refresh_mobile_window_mode(self):
        if platform != "android":
            return
        self._apply_android_fullscreen()

    @run_on_ui_thread
    def _apply_android_fullscreen(self):
        if platform != "android":
            return

        try:
            from jnius import autoclass

            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            View = autoclass("android.view.View")
            LayoutParams = autoclass("android.view.WindowManager$LayoutParams")
            activity = PythonActivity.mActivity
            window = activity.getWindow()
            decor_view = window.getDecorView()

            ui_flags = (
                View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                | View.SYSTEM_UI_FLAG_FULLSCREEN
                | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
            )
            window.addFlags(LayoutParams.FLAG_FULLSCREEN)
            decor_view.setSystemUiVisibility(ui_flags)
        except Exception:
            return


if __name__ == "__main__":
    _instance_guard = _SingleInstanceGuard("AliasOnlineDesktopAppMutex")
    if not _instance_guard.acquire():
        raise SystemExit(0)
    try:
        AliasApp().run()
    finally:
        _instance_guard.release()
