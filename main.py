import importlib
import importlib.util
import logging
import os
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import uuid
from contextlib import suppress
from pathlib import Path

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.utils import platform

logger = logging.getLogger(__name__)


def _ensure_android_site_packages_path():
    if platform != "android":
        return

    android_argument = os.environ.get("ANDROID_ARGUMENT")
    if not android_argument:
        return

    site_packages_dir = Path(android_argument) / "_python_bundle" / "site-packages"
    if site_packages_dir.exists():
        site_packages_str = str(site_packages_dir)
        if site_packages_str not in sys.path:
            sys.path.append(site_packages_str)


def _preload_kivy_input_package():
    """
    BlueStacks can intermittently fail importing `kivy.input` during SDL2 window init.
    We proactively load the package from the bundled .py/.pyc path so Window provider
    initialization does not abort with ModuleNotFoundError.
    """

    try:
        import kivy  # local import to keep startup ordering explicit
    except Exception as e:
        print(f"[STARTUP] Failed to import kivy: {e}", file=sys.stderr)
        return

    try:
        importlib.import_module("kivy.input")
        return
    except ModuleNotFoundError as exc:
        if getattr(exc, "name", "") != "kivy.input":
            return
        print(f"[STARTUP] kivy.input not found: {exc}", file=sys.stderr)
    except Exception as e:
        print(f"[STARTUP] Failed to import kivy.input: {e}", file=sys.stderr)
        return

    try:
        input_dir = Path(kivy.__file__).resolve().parent / "input"
        init_candidates = (input_dir / "__init__.py", input_dir / "__init__.pyc")
        init_path = next((candidate for candidate in init_candidates if candidate.exists()), None)
        if init_path is None:
            return

        spec = importlib.util.spec_from_file_location(
            "kivy.input",
            str(init_path),
            submodule_search_locations=[str(input_dir)],
        )
        if spec is None or spec.loader is None:
            return

        module = importlib.util.module_from_spec(spec)
        sys.modules["kivy.input"] = module
        spec.loader.exec_module(module)

        with suppress(Exception):
            importlib.import_module("kivy.input.provider")
    except Exception:
        sys.modules.pop("kivy.input", None)


_ensure_android_site_packages_path()
_preload_kivy_input_package()

try:
    from kivy.core.window import Window
except Exception as e:  # pragma: no cover - keep Android startup resilient
    print(f"[STARTUP] Failed to import kivy.core.window: {e}", file=sys.stderr)
    Window = None
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import FadeTransition, NoTransition, Screen, ScreenManager
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
        if platform == "android":
            Window.softinput_mode = "pan"
        else:
            Window.softinput_mode = "below_target"

if Window is not None and platform not in ("android", "ios"):
    with suppress(Exception):
        Window.size = (430, 820)

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
        self.guest_alias_coins = 0
        self.client_id = uuid.uuid4().hex
        self._guest_seed = (int(self.client_id[:6], 16) % 9000) + 1
        self.pending_registration_session_id = None
        self.active_room = {}
        self.active_room_player_name = None
        self._room_server_process = None
        self._room_server_thread = None
        self._embedded_room_server = None
        self._room_server_bootstrap_thread = None
        self.guest_room_lock_until = 0.0
        self.guest_room_lock_reason = None
        self._force_draw_event = None
        self._force_draw_until = 0.0
        self._lazy_screen_specs = {
            "create_room": ("screens.create_room", "CreateRoomScreen"),
            "join_room": ("screens.join_room", "JoinRoomScreen"),
            "friends": ("screens.friends", "FriendsScreen"),
            "rules": ("screens.rules", "RulesScreen"),
            "room": ("screens.room_screen", "RoomScreen"),
            "player_profile": ("screens.player_profile_screen", "PlayerProfileScreen"),
        }
        self._screen_warmup_queue = []
        self._screen_warmup_event = None
        self.screen_manager = None

    def build(self):
        try:
            register_game_font()
            initialize_database()
            # Give Android first frame time to render before heavy room-server bootstrap.
            startup_server_delay = 1.2 if platform in ("android", "ios") else 0
            Clock.schedule_once(lambda *_: self._start_room_server_in_background(), startup_server_delay)

            from screens.email_verification_screen import EmailVerificationScreen
            from screens.entry_screen import EntryScreen
            from screens.login_screen import LoginScreen
            from screens.password_recovery_screen import PasswordRecoveryScreen
            from screens.registration_screen import RegistrationScreen
            from screens.start_screen import StartScreen

            active_profile = get_active_profile()
            self.authenticated = active_profile is not None
            self.guest_mode = False

            transition = NoTransition() if platform == "android" else FadeTransition(duration=0.18)
            screen_manager = ScreenManager(transition=transition)
            self.screen_manager = screen_manager
            screen_manager.add_widget(EntryScreen(name="entry"))
            screen_manager.add_widget(LoginScreen(name="login"))
            screen_manager.add_widget(RegistrationScreen(name="registration"))
            screen_manager.add_widget(PasswordRecoveryScreen(name="password_recovery"))
            screen_manager.add_widget(EmailVerificationScreen(name="email_verification"))
            screen_manager.add_widget(StartScreen(name="start"))
            screen_manager.bind(current=self._guard_session)
            screen_manager.current = "start" if self.authenticated else "entry"
            warmup_delay = 0.55 if platform in ("android", "ios") else 0.15
            Clock.schedule_once(lambda *_: self._start_lazy_screen_warmup(), warmup_delay)
            return screen_manager
        except Exception as error:
            _log_unhandled_exception(type(error), error, error.__traceback__)
            return self._build_startup_error_screen(error)

    def _safe_start_room_server(self):
        try:
            self._ensure_local_room_server()
        except Exception as error:
            _log_unhandled_exception(type(error), error, error.__traceback__)

    def _start_room_server_in_background(self):
        existing_thread = self._room_server_bootstrap_thread
        if existing_thread is not None and existing_thread.is_alive():
            return

        bootstrap_thread = threading.Thread(
            target=self._safe_start_room_server,
            name="alias-room-bootstrap",
            daemon=True,
        )
        self._room_server_bootstrap_thread = bootstrap_thread
        bootstrap_thread.start()

    def ensure_local_room_server_ready(self, timeout=3.0):
        configured_url = room_server_url(refresh=True)
        if not is_local_room_server_url(configured_url):
            return True

        self._start_room_server_in_background()
        deadline = time.time() + max(0.2, float(timeout))
        while time.time() < deadline:
            if self._room_server_is_healthy(configured_url):
                return True
            time.sleep(0.1)
        return self._room_server_is_healthy(configured_url)

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
            with urllib.request.urlopen(health_url, timeout=5.0) as response:
                return response.status == 200
        except (urllib.error.URLError, TimeoutError) as e:
            # Local room server health check failure - not critical for startup
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
            except Exception as e:
                print(f"[ROOM_SERVER] Failed to import create_server: {e}", file=sys.stderr)
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
        server_env = os.environ.copy()
        # Prevent Kivy argument parser from intercepting room-server CLI flags.
        server_env.setdefault("KIVY_NO_ARGS", "1")
        try:
            self._room_server_process = subprocess.Popen(
                [sys.executable, str(server_script), "--host", bind_host, "--port", str(bind_port)],
                cwd=str(root_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
                env=server_env,
            )
        except OSError:
            self._room_server_process = None
            return

        return

    def on_stop(self):
        self._stop_lazy_screen_warmup()
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

    def resolve_room_player_name(self, room_code=None):
        active_room_code = ((self.active_room or {}).get("code") or "").strip().upper()
        target_room_code = (room_code or active_room_code or "").strip().upper()
        room_player_name = (self.active_room_player_name or "").strip()
        if room_player_name and (not target_room_code or target_room_code == active_room_code):
            return room_player_name
        return self.resolve_player_name()

    def resolve_client_id(self):
        return (self.client_id or "").strip()

    def adopt_room_player_name(self, player_name):
        clean_name = (player_name or "").strip()
        if not clean_name:
            return
        self.active_room_player_name = clean_name
        # Keep guest alias aligned with server-assigned guest names.
        if self.guest_mode:
            self.guest_name = clean_name

    def current_alias_coins(self):
        if self.authenticated:
            profile = self.current_profile()
            if profile is None:
                return 0
            try:
                return int(getattr(profile, "alias_coins", 0) or 0)
            except (TypeError, ValueError):
                return 0

        if self.guest_mode:
            try:
                return int(getattr(self, "guest_alias_coins", 0) or 0)
            except (TypeError, ValueError):
                return 0

        return 0

    def try_spend_guest_alias_coins(self, amount):
        charge = max(0, int(amount or 0))
        current = self.current_alias_coins()
        if not self.guest_mode:
            return False, current
        if charge == 0:
            return True, current
        if current < charge:
            return False, current
        self.guest_alias_coins = max(0, current - charge)
        return True, int(self.guest_alias_coins)

    def sign_in(self, profile=None):
        self.authenticated = profile is not None
        self.guest_mode = False
        self.guest_alias_coins = 0
        guest_number = self._guest_seed + self.guest_counter - 1
        self.guest_name = f"Гость{guest_number}"
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
        self.guest_alias_coins = 100
        guest_number = self._guest_seed + self.guest_counter - 1
        self.guest_name = f"Гость{guest_number}"
        self.clear_pending_registration_session()
        self.clear_active_room()

    def start_registration_flow(self):
        self.authenticated = False
        self.guest_mode = False
        self.guest_alias_coins = 0
        self.clear_pending_registration_session()
        set_active_profile(None)
        self.clear_active_room()

    def sign_out(self):
        self._leave_active_room()
        self.authenticated = False
        self.guest_mode = False
        self.guest_alias_coins = 0
        self.clear_pending_registration_session()
        set_active_profile(None)
        self.clear_active_room()

    def set_pending_registration_session(self, session_id):
        clean_session_id = (session_id or "").strip()
        self.pending_registration_session_id = clean_session_id or None

    def clear_pending_registration_session(self):
        if self.guest_mode:
            guest_number = self._guest_seed + max(0, self.guest_counter - 1)
            self.guest_name = f"Гость{guest_number}"
        self.pending_registration_session_id = None

    def set_active_room(self, room):
        previous_room_code = ((self.active_room or {}).get("code") or "").strip().upper()
        self.active_room = dict(room or {})
        current_room_code = ((self.active_room or {}).get("code") or "").strip().upper()
        joined_as = (self.active_room.get("_joined_as") or "").strip()
        if not joined_as:
            server_state = self.active_room.get("_server_state")
            if isinstance(server_state, dict):
                viewer = server_state.get("viewer")
                if isinstance(viewer, dict):
                    joined_as = (viewer.get("player_name") or "").strip()
        if joined_as:
            self.active_room_player_name = joined_as
        elif previous_room_code and current_room_code and previous_room_code != current_room_code:
            self.active_room_player_name = None

    def get_active_room(self):
        return dict(self.active_room or {})

    def clear_active_room(self):
        self.active_room = {}
        self.active_room_player_name = None

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
        player_name = self.resolve_room_player_name(room_code=room_code)
        if not room_code or not player_name:
            return

        try:
            leave_online_room(
                room_code=room_code,
                player_name=player_name,
                client_id=self.resolve_client_id(),
            )
        except (ConnectionError, ValueError):
            pass

    def _guard_session(self, manager, current_screen_name):
        if current_screen_name in {"entry", "login", "registration", "email_verification", "password_recovery"}:
            return

        if not self.has_session_access():
            manager.current = "entry"

    def on_start(self):
        if platform == "android":
            self._prime_startup_redraw(4.0)
            if os.getenv("ALIAS_DEBUG_UI_DUMP", "").strip() == "1":
                Clock.schedule_once(lambda *_: self._debug_dump_ui("start+1s"), 1.0)
                Clock.schedule_once(lambda *_: self._debug_dump_ui("start+5s"), 5.0)
                Clock.schedule_once(lambda *_: self._debug_dump_ui("start+12s"), 12.0)
        return

    def ensure_screen(self, screen_name):
        manager = self.root if isinstance(self.root, ScreenManager) else self.screen_manager
        if manager is None:
            return None

        if screen_name in manager.screen_names:
            return manager.get_screen(screen_name)

        screen_spec = self._lazy_screen_specs.get(screen_name)
        if screen_spec is None:
            return None

        module_name, class_name = screen_spec
        module = importlib.import_module(module_name)
        screen_class = getattr(module, class_name)
        screen = screen_class(name=screen_name)
        manager.add_widget(screen)
        return screen

    def _start_lazy_screen_warmup(self):
        self._stop_lazy_screen_warmup()
        manager = self.root if isinstance(self.root, ScreenManager) else self.screen_manager
        if manager is None:
            return

        self._screen_warmup_queue = [
            name for name in self._lazy_screen_specs.keys() if name not in manager.screen_names
        ]
        if not self._screen_warmup_queue:
            return

        self._screen_warmup_event = Clock.schedule_interval(self._warmup_next_screen, 0.03)

    def _stop_lazy_screen_warmup(self):
        if self._screen_warmup_event is not None:
            self._screen_warmup_event.cancel()
            self._screen_warmup_event = None
        self._screen_warmup_queue = []

    def _warmup_next_screen(self, _dt):
        if not self._screen_warmup_queue:
            self._stop_lazy_screen_warmup()
            return False

        next_screen = self._screen_warmup_queue.pop(0)
        try:
            self.ensure_screen(next_screen)
        except Exception:
            pass

        if not self._screen_warmup_queue:
            self._stop_lazy_screen_warmup()
            return False
        return True

    def on_resume(self):
        if platform == "android":
            self._prime_startup_redraw(2.5)
            if os.getenv("ALIAS_DEBUG_UI_DUMP", "").strip() == "1":
                Clock.schedule_once(lambda *_: self._debug_dump_ui("resume+0.5s"), 0.5)
        return True

    def _prime_startup_redraw(self, duration_seconds):
        self._stop_force_draw()
        self._force_draw_until = time.time() + max(2.0, float(duration_seconds))
        self._force_draw_event = Clock.schedule_interval(self._force_redraw_tick, 1 / 20.0)

    def _stop_force_draw(self):
        if self._force_draw_event is not None:
            self._force_draw_event.cancel()
            self._force_draw_event = None

    def _force_redraw_tick(self, _dt):
        if time.time() >= self._force_draw_until:
            self._stop_force_draw()
            return False

        root = self.root
        if root is not None:
            with suppress(Exception):
                root.canvas.ask_update()

            active_screen = getattr(root, "current_screen", None)
            if active_screen is not None:
                with suppress(Exception):
                    active_screen.canvas.ask_update()
                self._stabilize_active_screen(active_screen)
                for child in active_screen.children[:4]:
                    with suppress(Exception):
                        child.canvas.ask_update()

        if Window is not None:
            with suppress(Exception):
                Window.canvas.ask_update()
        return True

    @staticmethod
    def _stabilize_active_screen(screen):
        screen_size = tuple(screen.size)
        if screen_size[0] <= 0 or screen_size[1] <= 0:
            return

        for child in screen.children:
            size_hint = getattr(child, "size_hint", None)
            if size_hint is None:
                continue
            if tuple(size_hint) != (1, 1):
                continue

            child_size = tuple(child.size)
            if child_size[0] >= screen_size[0] * 0.92 and child_size[1] >= screen_size[1] * 0.92:
                continue

            child.pos = screen.pos
            child.size = screen.size

    def _debug_dump_ui(self, tag):
        try:
            root = self.root
            current = getattr(root, "current", "<no-manager>")
            screen_names = getattr(root, "screen_names", [])
            logger.debug(f"[ALIAS_UI] {tag} current={current} screens={list(screen_names)}")
            if root is None:
                return

            screen = root.get_screen(current) if current in screen_names else None
            if screen is None:
                logger.debug(f"[ALIAS_UI] {tag} no-active-screen")
                return

            child_count = len(screen.children)
            logger.debug(f"[ALIAS_UI] {tag} screen={screen.name} size={tuple(screen.size)} children={child_count}")
            for index, child in enumerate(screen.children[:4]):
                logger.debug(
                    f"[ALIAS_UI] {tag} child[{index}]={child.__class__.__name__} "
                    f"size={tuple(child.size)} pos={tuple(child.pos)} opacity={getattr(child, 'opacity', 1)}"
                )
        except Exception as error:
            logger.debug(f"[ALIAS_UI] {tag} dump-error={error}")


if __name__ == "__main__":
    _instance_guard = _SingleInstanceGuard("AliasOnlineDesktopAppMutex")
    if not _instance_guard.acquire():
        raise SystemExit(0)
    try:
        try:
            AliasApp().run()
        except KeyboardInterrupt:
            # Graceful terminal stop (Ctrl+C / forced console interrupt) without traceback noise.
            pass
    finally:
        _instance_guard.release()
