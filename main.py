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
from screens.rules import RulesScreen
from screens.start_screen import StartScreen
from services import get_active_profile, initialize_database, set_active_profile
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

    def build(self):
        register_game_font()
        initialize_database()

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
        screen_manager.bind(current=self._guard_session)
        screen_manager.current = "start" if self.authenticated else "entry"
        return screen_manager

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

        if profile is not None:
            set_active_profile(profile.email)
        else:
            set_active_profile(None)

    def enter_guest_mode(self):
        self.authenticated = False
        self.guest_mode = True
        self.guest_counter += 1
        self.guest_name = f"Гость{self.guest_counter}"

    def start_registration_flow(self):
        self.authenticated = False
        self.guest_mode = False
        set_active_profile(None)

    def sign_out(self):
        self.authenticated = False
        self.guest_mode = False
        set_active_profile(None)

    def _guard_session(self, manager, current_screen_name):
        if current_screen_name in {"entry", "login", "registration"}:
            return

        if not self.has_session_access():
            manager.current = "entry"


if __name__ == "__main__":
    AliasApp().run()
