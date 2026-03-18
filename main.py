import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from kivy.app import App
from kivy.core.window import Window
from kivy.uix.screenmanager import FadeTransition, ScreenManager
from kivy.utils import platform

from screens.create_room import CreateRoomScreen
from screens.entry_screen import EntryScreen
from screens.friends import FriendsScreen
from screens.join_room import JoinRoomScreen
from screens.login_screen import LoginScreen
from screens.registration_screen import RegistrationScreen
from screens.room_screen import RoomScreen
from screens.rules import RulesScreen
from screens.start_screen import StartScreen
from services import get_active_profile, initialize_database, leave_online_room, set_active_profile
from ui.theme import register_game_font

Window.title = "Alias Online"
Window.softinput_mode = "below_target"

if platform not in ("android", "ios"):
    Window.size = (430, 820)


class AliasApp(App):
    guest_name = "Гость"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.authenticated = False
        self.guest_mode = False
        self.guest_counter = 0
        self.active_room = {}
        self._room_server_process = None

    def build(self):
        register_game_font()
        initialize_database()
        self._ensure_local_room_server()

        active_profile = get_active_profile()
        self.authenticated = active_profile is not None
        self.guest_mode = False

        screen_manager = ScreenManager(transition=FadeTransition(duration=0.18))
        screen_manager.add_widget(EntryScreen(name="entry"))
        screen_manager.add_widget(LoginScreen(name="login"))
        screen_manager.add_widget(RegistrationScreen(name="registration"))
        screen_manager.add_widget(StartScreen(name="start"))
        screen_manager.add_widget(CreateRoomScreen(name="create_room"))
        screen_manager.add_widget(JoinRoomScreen(name="join_room"))
        screen_manager.add_widget(FriendsScreen(name="friends"))
        screen_manager.add_widget(RulesScreen(name="rules"))
        screen_manager.add_widget(RoomScreen(name="room"))
        screen_manager.bind(current=self._guard_session)
        screen_manager.current = "start" if self.authenticated else "entry"
        return screen_manager

    def _room_server_is_healthy(self):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=1.2) as response:
                return response.status == 200
        except (urllib.error.URLError, TimeoutError):
            return False

    def _ensure_local_room_server(self):
        if platform in ("android", "ios"):
            return
        if self._room_server_is_healthy():
            return

        root_dir = Path(__file__).resolve().parent
        server_script = root_dir / "server" / "room_server.py"
        if not server_script.exists():
            return

        creation_flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        try:
            self._room_server_process = subprocess.Popen(
                [sys.executable, str(server_script), "--host", "127.0.0.1", "--port", "8765"],
                cwd=str(root_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
            )
        except OSError:
            self._room_server_process = None
            return

        for _ in range(18):
            if self._room_server_is_healthy():
                return
            time.sleep(0.2)

    def on_stop(self):
        self._leave_active_room()
        process = self._room_server_process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1.2)
            except subprocess.TimeoutExpired:
                process.kill()

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
        self.clear_active_room()

    def start_registration_flow(self):
        self.authenticated = False
        self.guest_mode = False
        set_active_profile(None)
        self.clear_active_room()

    def sign_out(self):
        self._leave_active_room()
        self.authenticated = False
        self.guest_mode = False
        set_active_profile(None)
        self.clear_active_room()

    def set_active_room(self, room):
        self.active_room = dict(room or {})

    def get_active_room(self):
        return dict(self.active_room or {})

    def clear_active_room(self):
        self.active_room = {}

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
        if current_screen_name in {"entry", "login", "registration"}:
            return

        if not self.has_session_access():
            manager.current = "entry"


if __name__ == "__main__":
    AliasApp().run()
