from functools import partial

from kivy.app import App
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from services import add_friend, list_friend_profiles, search_profiles
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


class FriendsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        register_game_font()

        root = ScreenBackground()
        scroll, content = build_scrollable_content()

        back_btn = AppButton(text="Назад", compact=True, size_hint_x=None, width=dp(132))
        back_btn.bind(on_release=lambda *_: setattr(self.manager, "current", "start"))
        content.add_widget(back_btn)
        content.add_widget(BrandTitle(text="ALIAS ONLINE", height=dp(136), font_size=sp(44), shadow_step=dp(3)))
        content.add_widget(PixelLabel(text="Друзья", font_size=sp(20), center=True))

        search_card = RoundedPanel(
            orientation="vertical",
            padding=[dp(14), dp(12), dp(14), dp(12)],
            spacing=dp(8),
            size_hint_y=None,
            height=dp(152),
        )
        search_card.add_widget(PixelLabel(text="Найти друга", font_size=sp(13), center=True))

        search_row = BoxLayout(orientation="horizontal", spacing=dp(10), size_hint_y=None, height=dp(46))
        self.search_input = AppTextInput(hint_text="Код или никнейм", height=dp(44))
        search_row.add_widget(self.search_input)
        self.search_btn = AppButton(
            text="Найти",
            compact=True,
            font_size=sp(14),
            size_hint=(None, None),
            size=(dp(114), dp(42)),
        )
        self.search_btn.bind(on_release=self.perform_search)
        search_row.add_widget(self.search_btn)
        search_card.add_widget(search_row)

        self.search_status = BodyLabel(
            center=True,
            color=COLORS["text_muted"],
            font_size=sp(11),
            auto_height=False,
            size_hint_y=None,
            height=dp(34),
            text="",
        )
        search_card.add_widget(self.search_status)
        content.add_widget(search_card)

        self.search_results_card_height = dp(230)
        self.search_results_card = RoundedPanel(
            orientation="vertical",
            padding=[dp(14), dp(10), dp(14), dp(10)],
            spacing=dp(8),
            size_hint_y=None,
            height=dp(0),
            opacity=0,
            disabled=True,
        )
        self.search_results_card.add_widget(PixelLabel(text="Результаты поиска", font_size=sp(13), center=True))
        self.search_results_scroll = ScrollView(
            do_scroll_x=False,
            scroll_type=["bars", "content"],
            bar_width=dp(4),
            size_hint_y=None,
            height=dp(170),
        )
        self.search_results_box = BoxLayout(
            orientation="vertical",
            spacing=dp(10),
            size_hint_y=None,
        )
        self.search_results_box.bind(minimum_height=self.search_results_box.setter("height"))
        self.search_results_scroll.add_widget(self.search_results_box)
        self.search_results_card.add_widget(self.search_results_scroll)
        content.add_widget(self.search_results_card)

        friends_card = RoundedPanel(
            orientation="vertical",
            padding=[dp(16), dp(16), dp(16), dp(16)],
            spacing=dp(10),
            size_hint_y=None,
        )
        friends_card.bind(minimum_height=friends_card.setter("height"))
        friends_card.add_widget(PixelLabel(text="Список друзей", font_size=sp(14), center=True))

        self.friends_status = BodyLabel(
            center=True,
            color=COLORS["text_muted"],
            font_size=sp(12),
            text="",
        )
        friends_card.add_widget(self.friends_status)

        self.friends_box = BoxLayout(
            orientation="vertical",
            spacing=dp(10),
            size_hint_y=None,
        )
        self.friends_box.bind(minimum_height=self.friends_box.setter("height"))
        friends_card.add_widget(self.friends_box)
        content.add_widget(friends_card)

        root.add_widget(scroll)
        self.coin_badge = CoinBadge(pos_hint={"right": 0.965, "top": 0.96})
        root.add_widget(self.coin_badge)
        self.add_widget(root)

    def on_pre_enter(self, *_):
        self.coin_badge.refresh_from_session()
        self.search_input.text = ""
        self._clear_box(self.search_results_box)
        self._set_search_results_visible(False)
        self._refresh_view()

    def _set_search_results_visible(self, visible):
        self.search_results_card.disabled = not visible
        self.search_results_card.opacity = 1 if visible else 0
        self.search_results_card.height = self.search_results_card_height if visible else dp(0)

    def perform_search(self, *_):
        profile = self._current_profile()
        if profile is None:
            self.search_status.color = COLORS["warning"]
            self.search_status.text = "Поиск друзей доступен только для зарегистрированного аккаунта."
            return

        query = self.search_input.text.strip()
        if not query:
            self.search_status.color = COLORS["warning"]
            self.search_status.text = "Введи код друга или никнейм."
            self._clear_box(self.search_results_box)
            self._set_search_results_visible(False)
            return

        matches = search_profiles(query, exclude_email=profile.email)
        self._clear_box(self.search_results_box)
        self._set_search_results_visible(False)

        if not matches:
            self.search_status.color = COLORS["warning"]
            self.search_status.text = "Ничего не найдено. Проверь код или никнейм."
            return

        self.search_status.color = COLORS["success"]
        self.search_status.text = "Пользователи найдены. Можно добавить в друзья."
        self._set_search_results_visible(True)
        for found_profile in matches:
            self.search_results_box.add_widget(
                self._build_profile_card(
                    found_profile,
                    button_text="Добавить",
                    button_handler=partial(self._add_friend, found_profile.email),
                )
            )

    def _refresh_view(self):
        profile = self._current_profile()
        self._clear_box(self.friends_box)
        self._clear_box(self.search_results_box)
        self._set_search_results_visible(False)

        if profile is None:
            self.search_input.disabled = True
            self.search_btn.disabled = True
            self.search_status.color = COLORS["warning"]
            self.search_status.text = "Гостям раздел друзей недоступен."
            self.friends_status.color = COLORS["text_muted"]
            self.friends_status.text = "Войди в аккаунт, чтобы искать и добавлять друзей."
            return

        self.search_input.disabled = False
        self.search_btn.disabled = False
        self.search_status.color = COLORS["text_muted"]
        self.search_status.text = "Введи код или никнейм друга."

        friends = list_friend_profiles(profile.email)
        if not friends:
            self.friends_status.color = COLORS["text_muted"]
            self.friends_status.text = "Список друзей пока пуст."
            return

        self.friends_status.color = COLORS["success"]
        self.friends_status.text = f"Всего друзей: {len(friends)}"
        for friend_profile in friends:
            self.friends_box.add_widget(self._build_profile_card(friend_profile))

    def _add_friend(self, friend_email, *_):
        profile = self._current_profile()
        if profile is None:
            self.search_status.color = COLORS["warning"]
            self.search_status.text = "Сначала войди в аккаунт."
            return

        try:
            added_profile = add_friend(profile.email, friend_email)
        except ValueError as error:
            self.search_status.color = COLORS["warning"]
            self.search_status.text = str(error)
            return

        self.search_status.color = COLORS["success"]
        self.search_status.text = f"{added_profile.name} добавлен в друзья."
        self._refresh_view()

    def _build_profile_card(self, profile, button_text=None, button_handler=None):
        panel = RoundedPanel(
            orientation="horizontal",
            padding=[dp(14), dp(12), dp(14), dp(12)],
            spacing=dp(12),
            size_hint_y=None,
            height=dp(88),
        )

        info = BoxLayout(orientation="vertical", spacing=dp(4))
        info.add_widget(PixelLabel(text=profile.name, font_size=sp(16), size_hint_y=None))
        info.add_widget(
            BodyLabel(
                color=COLORS["text_muted"],
                font_size=sp(12),
                text=f"Код: {profile.id}",
            )
        )
        panel.add_widget(info)

        if button_text and button_handler is not None:
            action_btn = AppButton(
                text=button_text,
                compact=True,
                font_size=sp(14),
                size_hint=(None, None),
                size=(dp(132), dp(46)),
            )
            action_btn.bind(on_release=button_handler)
            panel.add_widget(action_btn)
        else:
            panel.add_widget(Widget(size_hint_x=None, width=dp(8)))

        return panel

    def _clear_box(self, box):
        box.clear_widgets()

    def _current_profile(self):
        app = App.get_running_app()
        return app.current_profile() if app is not None else None
