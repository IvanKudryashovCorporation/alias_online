from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from services import (
    add_friend,
    block_profile,
    get_profile_by_email,
    get_profile_by_name,
    get_relationship_state,
    list_friend_messages,
    report_profile,
    send_friend_message,
)
from ui import (
    AppButton,
    AppTextInput,
    AvatarButton,
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


class StatChip(RoundedPanel):
    def __init__(self, title, **kwargs):
        super().__init__(
            orientation="vertical",
            spacing=dp(0),
            padding=[dp(8), dp(6), dp(8), dp(6)],
            size_hint=(None, None),
            size=(dp(126), dp(50)),
            bg_color=COLORS["surface_panel"],
            shadow_alpha=0.10,
            **kwargs,
        )
        self.title_label = BodyLabel(text=title, center=True, color=COLORS["text_muted"], font_size=sp(9), size_hint_y=None)
        self.value_label = PixelLabel(text="0", center=True, font_size=sp(14), size_hint_y=None)
        self.add_widget(self.title_label)
        self.add_widget(self.value_label)

    def set_value(self, value):
        self.value_label.text = str(int(value or 0))


class PlayerProfileScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        register_game_font()
        self.target_player_name = ""
        self.target_player_email = ""
        self.return_screen = "start"
        self.target_profile = None
        self.messages_popup = None
        self.messages_box = None
        self.messages_scroll = None
        self.messages_input = None
        self.messages_status = None
        self.report_popup = None

        root = ScreenBackground()
        scroll, content = build_scrollable_content(
            padding=[dp(18), dp(16), dp(18), dp(20)],
            spacing=dp(10),
        )

        top_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48))
        self.back_btn = AppButton(text="Назад", compact=True, size_hint=(None, None), size=(dp(126), dp(44)))
        self.back_btn.bind(on_release=self._go_back)
        top_row.add_widget(self.back_btn)
        top_row.add_widget(Widget())
        content.add_widget(top_row)

        content.add_widget(BrandTitle(text="ALIAS ONLINE", height=dp(98), font_size=sp(34), shadow_step=dp(2.5)))
        content.add_widget(PixelLabel(text="Профиль игрока", font_size=sp(20), center=True, size_hint_y=None))

        self.screen_status = BodyLabel(
            center=True,
            color=COLORS["text_muted"],
            font_size=sp(11.5),
            size_hint_y=None,
            text="",
        )
        content.add_widget(self.screen_status)

        self.profile_card = RoundedPanel(
            orientation="vertical",
            spacing=dp(10),
            padding=[dp(16), dp(14), dp(16), dp(14)],
            size_hint_y=None,
        )
        self.profile_card.bind(minimum_height=self.profile_card.setter("height"))

        profile_top = BoxLayout(orientation="horizontal", spacing=dp(12), size_hint_y=None, height=dp(74))
        self.avatar = AvatarButton()
        self.avatar.size = (dp(70), dp(70))
        self.avatar.disabled = True
        profile_top.add_widget(self.avatar)

        profile_meta = BoxLayout(orientation="vertical", spacing=dp(2))
        self.name_label = PixelLabel(text="—", font_size=sp(22), size_hint_y=None)
        profile_meta.add_widget(self.name_label)
        self.code_label = BodyLabel(text="", color=COLORS["text_muted"], font_size=sp(11), size_hint_y=None)
        profile_meta.add_widget(self.code_label)
        self.bio_label = BodyLabel(text="", color=COLORS["text_soft"], font_size=sp(11), size_hint_y=None)
        profile_meta.add_widget(self.bio_label)
        profile_top.add_widget(profile_meta)
        self.profile_card.add_widget(profile_top)

        stats_row_1 = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(52))
        stats_row_1.add_widget(Widget())
        self.games_chip = StatChip("Игр")
        stats_row_1.add_widget(self.games_chip)
        self.total_chip = StatChip("Очков")
        stats_row_1.add_widget(self.total_chip)
        stats_row_1.add_widget(Widget())
        self.profile_card.add_widget(stats_row_1)

        stats_row_2 = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(52))
        stats_row_2.add_widget(Widget())
        self.guessed_chip = StatChip("Угадано")
        stats_row_2.add_widget(self.guessed_chip)
        self.explained_chip = StatChip("Объяснено")
        stats_row_2.add_widget(self.explained_chip)
        stats_row_2.add_widget(Widget())
        self.profile_card.add_widget(stats_row_2)
        content.add_widget(self.profile_card)

        self.actions_card = RoundedPanel(
            orientation="vertical",
            spacing=dp(10),
            padding=[dp(14), dp(14), dp(14), dp(14)],
            size_hint_y=None,
        )
        self.actions_card.bind(minimum_height=self.actions_card.setter("height"))
        self.actions_card.add_widget(PixelLabel(text="Действия", font_size=sp(14), center=True, size_hint_y=None))

        self.add_friend_btn = AppButton(text="Добавить в друзья", compact=True, font_size=sp(14))
        self.add_friend_btn.bind(on_release=self._add_friend)
        self.actions_card.add_widget(self.add_friend_btn)

        self.message_btn = AppButton(text="Написать", compact=True, font_size=sp(14))
        self.message_btn.bind(on_release=self._open_messages_popup)
        self.actions_card.add_widget(self.message_btn)

        self.block_btn = AppButton(
            text="Заблокировать",
            compact=True,
            font_size=sp(14),
            button_color=COLORS["danger_button"],
            pressed_color=COLORS["danger_button_pressed"],
        )
        self.block_btn.bind(on_release=self._block_target)
        self.actions_card.add_widget(self.block_btn)

        self.report_btn = AppButton(text="Пожаловаться", compact=True, font_size=sp(14))
        self.report_btn.bind(on_release=self._open_report_popup)
        self.actions_card.add_widget(self.report_btn)

        self.action_status = BodyLabel(
            center=True,
            color=COLORS["text_muted"],
            font_size=sp(11),
            size_hint_y=None,
            text="",
        )
        self.actions_card.add_widget(self.action_status)
        content.add_widget(self.actions_card)

        root.add_widget(scroll)
        self.coin_badge = CoinBadge(pos_hint={"right": 0.965, "top": 0.96})
        root.add_widget(self.coin_badge)
        self.add_widget(root)

    def open_for_player(self, player_name=None, player_email=None, return_screen="start"):
        self.target_player_name = (player_name or "").strip()
        self.target_player_email = (player_email or "").strip().lower()
        self.return_screen = return_screen or "start"

    def on_pre_enter(self, *_):
        self.coin_badge.refresh_from_session()
        self._refresh_view()

    def on_leave(self, *_):
        self._dismiss_messages_popup()
        self._dismiss_report_popup()

    def _current_profile(self):
        app = App.get_running_app()
        if app is None or not getattr(app, "authenticated", False):
            return None
        return app.current_profile()

    def _load_target_profile(self):
        if self.target_player_email:
            return get_profile_by_email(self.target_player_email)
        if self.target_player_name:
            return get_profile_by_name(self.target_player_name)
        return None

    def _refresh_view(self):
        viewer = self._current_profile()
        target = self._load_target_profile()
        self.target_profile = target
        self.action_status.text = ""

        if viewer is None:
            self.screen_status.color = COLORS["warning"]
            self.screen_status.text = "Войти в профиль игрока можно только из авторизованного аккаунта."
            self._apply_profile_placeholder()
            self._set_actions_enabled(False)
            return

        if target is None:
            self.screen_status.color = COLORS["warning"]
            self.screen_status.text = "Профиль не найден. У гостей и ботов профиля нет."
            self._apply_profile_placeholder()
            self._set_actions_enabled(False)
            return

        self.avatar.set_profile(target)
        self.name_label.text = target.name
        self.code_label.text = f"Код игрока #{target.id}"
        self.bio_label.text = (target.bio or "Описание не заполнено.").strip()
        self.games_chip.set_value(target.games_played)
        self.total_chip.set_value(target.total_points)
        self.guessed_chip.set_value(target.guessed_words)
        self.explained_chip.set_value(target.explained_words)
        self.screen_status.color = COLORS["text_muted"]
        self.screen_status.text = "Нажми на действие ниже."

        relation = get_relationship_state(viewer.email, target.email)
        is_self = relation.get("is_self", False)
        is_friend = relation.get("is_friend", False)
        blocked_by_viewer = relation.get("blocked_by_viewer", False)
        blocked_viewer = relation.get("blocked_viewer", False)

        if is_friend:
            self.add_friend_btn.text = "Уже в друзьях"
        elif blocked_by_viewer:
            self.add_friend_btn.text = "Игрок заблокирован"
        elif blocked_viewer:
            self.add_friend_btn.text = "Взаимодействие ограничено"
        else:
            self.add_friend_btn.text = "Добавить в друзья"

        self.add_friend_btn.disabled = not relation.get("can_add_friend", False)
        self.message_btn.disabled = not relation.get("can_message", False)
        self.block_btn.disabled = is_self or blocked_by_viewer
        self.report_btn.disabled = is_self
        self.message_btn.text = "Написать" if not self.message_btn.disabled else "Писать нельзя"
        self.block_btn.text = "Заблокирован" if blocked_by_viewer else "Заблокировать"

        if blocked_viewer:
            self.action_status.color = COLORS["warning"]
            self.action_status.text = "Этот игрок ограничил взаимодействие с тобой."
        elif blocked_by_viewer:
            self.action_status.color = COLORS["warning"]
            self.action_status.text = "Игрок заблокирован. Писать и добавлять в друзья нельзя."
        elif is_friend:
            self.action_status.color = COLORS["success"]
            self.action_status.text = "Вы в друзьях. Можно писать сообщения."
        else:
            self.action_status.color = COLORS["text_muted"]
            self.action_status.text = "Можно добавить игрока в друзья."

    def _apply_profile_placeholder(self):
        self.avatar.set_profile(None)
        self.name_label.text = "—"
        self.code_label.text = ""
        self.bio_label.text = ""
        self.games_chip.set_value(0)
        self.total_chip.set_value(0)
        self.guessed_chip.set_value(0)
        self.explained_chip.set_value(0)

    def _set_actions_enabled(self, enabled):
        self.add_friend_btn.disabled = not enabled
        self.message_btn.disabled = not enabled
        self.block_btn.disabled = not enabled
        self.report_btn.disabled = not enabled

    def _add_friend(self, *_):
        viewer = self._current_profile()
        target = self.target_profile
        if viewer is None or target is None:
            return
        try:
            add_friend(viewer.email, target.email)
        except ValueError as error:
            self.action_status.color = COLORS["warning"]
            self.action_status.text = str(error)
            return

        self.action_status.color = COLORS["success"]
        self.action_status.text = f"{target.name} добавлен в друзья."
        self._refresh_view()

    def _block_target(self, *_):
        viewer = self._current_profile()
        target = self.target_profile
        if viewer is None or target is None:
            return
        try:
            block_profile(viewer.email, target.email)
        except ValueError as error:
            self.action_status.color = COLORS["warning"]
            self.action_status.text = str(error)
            return

        self.action_status.color = COLORS["success"]
        self.action_status.text = f"{target.name} заблокирован."
        self._dismiss_messages_popup()
        self._refresh_view()

    def _open_report_popup(self, *_):
        viewer = self._current_profile()
        target = self.target_profile
        if viewer is None or target is None:
            return

        self._dismiss_report_popup()
        body = BoxLayout(orientation="vertical", spacing=dp(10), padding=[dp(16), dp(16), dp(16), dp(16)])
        panel = RoundedPanel(
            orientation="vertical",
            spacing=dp(10),
            padding=[dp(14), dp(14), dp(14), dp(14)],
            size_hint_y=None,
            height=dp(356),
        )
        panel.add_widget(PixelLabel(text=f"Жалоба на {target.name}", font_size=sp(16), center=True, size_hint_y=None))

        reason_input = AppTextInput(hint_text="Причина (например: оскорбления)", height=dp(46))
        panel.add_widget(reason_input)
        details_input = AppTextInput(hint_text="Описание (необязательно)", multiline=True, height=dp(112))
        panel.add_widget(details_input)

        status_label = BodyLabel(center=True, color=COLORS["text_muted"], font_size=sp(11), size_hint_y=None, text="")
        panel.add_widget(status_label)

        actions = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(44))
        submit_btn = AppButton(text="Отправить", compact=True, font_size=sp(13), size_hint=(1, None), height=dp(42))
        cancel_btn = AppButton(text="Отмена", compact=True, font_size=sp(13), size_hint=(1, None), height=dp(42))
        submit_btn.bind(
            on_release=lambda *_: self._submit_report(reason_input.text, details_input.text, status_label)
        )
        cancel_btn.bind(on_release=lambda *_: self._dismiss_report_popup())
        actions.add_widget(submit_btn)
        actions.add_widget(cancel_btn)
        panel.add_widget(actions)
        body.add_widget(panel)

        self.report_popup = Popup(
            title="",
            separator_height=0,
            auto_dismiss=True,
            background="atlas://data/images/defaulttheme/modalview-background",
            content=body,
            size_hint=(0.86, None),
            height=dp(392),
        )
        self.report_popup.bind(on_dismiss=lambda *_: setattr(self, "report_popup", None))
        self.report_popup.open()

    def _submit_report(self, reason, details, status_label):
        viewer = self._current_profile()
        target = self.target_profile
        if viewer is None or target is None:
            return

        try:
            report_profile(viewer.email, target.email, reason=reason, details=details)
        except ValueError as error:
            status_label.color = COLORS["warning"]
            status_label.text = str(error)
            return

        status_label.color = COLORS["success"]
        status_label.text = "Жалоба отправлена."
        self.action_status.color = COLORS["success"]
        self.action_status.text = "Жалоба отправлена модерации."
        Clock.schedule_once(lambda *_: self._dismiss_report_popup(), 0.6)

    def _dismiss_report_popup(self):
        if self.report_popup is not None:
            popup = self.report_popup
            self.report_popup = None
            popup.dismiss()

    def _open_messages_popup(self, *_):
        viewer = self._current_profile()
        target = self.target_profile
        if viewer is None or target is None:
            return

        relation = get_relationship_state(viewer.email, target.email)
        if not relation.get("can_message"):
            self.action_status.color = COLORS["warning"]
            self.action_status.text = "Писать можно только друзьям без блокировки."
            return

        self._dismiss_messages_popup()
        body = BoxLayout(orientation="vertical", spacing=dp(10), padding=[dp(16), dp(16), dp(16), dp(16)])
        panel = RoundedPanel(
            orientation="vertical",
            spacing=dp(10),
            padding=[dp(12), dp(12), dp(12), dp(12)],
            size_hint_y=None,
            height=dp(458),
        )
        panel.add_widget(PixelLabel(text=f"Чат с {target.name}", font_size=sp(16), center=True, size_hint_y=None))

        self.messages_scroll = ScrollView(
            do_scroll_x=False,
            scroll_type=["bars", "content"],
            bar_width=dp(4),
            size_hint_y=None,
            height=dp(270),
        )
        self.messages_box = BoxLayout(orientation="vertical", spacing=dp(6), size_hint_y=None)
        self.messages_box.bind(minimum_height=self.messages_box.setter("height"))
        self.messages_scroll.add_widget(self.messages_box)
        panel.add_widget(self.messages_scroll)

        self.messages_status = BodyLabel(center=True, color=COLORS["text_muted"], font_size=sp(10.5), size_hint_y=None, text="")
        panel.add_widget(self.messages_status)

        row = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(44))
        self.messages_input = AppTextInput(hint_text="Сообщение...", height=dp(42))
        row.add_widget(self.messages_input)
        send_btn = AppButton(text="Отправить", compact=True, font_size=sp(13), size_hint=(None, None), size=(dp(114), dp(42)))
        send_btn.bind(on_release=self._send_message_from_popup)
        row.add_widget(send_btn)
        panel.add_widget(row)

        close_btn = AppButton(text="Закрыть", compact=True, font_size=sp(13), size_hint_y=None, height=dp(40))
        close_btn.bind(on_release=lambda *_: self._dismiss_messages_popup())
        panel.add_widget(close_btn)
        body.add_widget(panel)

        self.messages_popup = Popup(
            title="",
            separator_height=0,
            auto_dismiss=True,
            background="atlas://data/images/defaulttheme/modalview-background",
            content=body,
            size_hint=(0.9, None),
            height=dp(490),
        )
        self.messages_popup.bind(on_dismiss=lambda *_: self._clear_messages_popup_refs())
        self.messages_popup.open()
        self._refresh_messages_popup()

    def _refresh_messages_popup(self):
        if self.messages_box is None:
            return
        viewer = self._current_profile()
        target = self.target_profile
        if viewer is None or target is None:
            return

        messages = list_friend_messages(viewer.email, target.email, limit=120)
        self.messages_box.clear_widgets()
        if not messages:
            self.messages_box.add_widget(
                BodyLabel(
                    center=True,
                    color=COLORS["text_muted"],
                    font_size=sp(11),
                    text="Пока нет сообщений.",
                    size_hint_y=None,
                )
            )
        else:
            for message in messages:
                prefix = "Ты" if message.get("is_outgoing") else target.name
                text_color = COLORS["text_soft"] if message.get("is_outgoing") else COLORS["text"]
                self.messages_box.add_widget(
                    BodyLabel(
                        text=f"{prefix}: {message.get('message', '')}",
                        color=text_color,
                        font_size=sp(11),
                        size_hint_y=None,
                    )
                )
        if self.messages_status is not None:
            self.messages_status.text = f"Сообщений: {len(messages)}"
            self.messages_status.color = COLORS["text_muted"]
        Clock.schedule_once(lambda *_: setattr(self.messages_scroll, "scroll_y", 0), 0)

    def _send_message_from_popup(self, *_):
        viewer = self._current_profile()
        target = self.target_profile
        if viewer is None or target is None or self.messages_input is None:
            return
        text = (self.messages_input.text or "").strip()
        if not text:
            if self.messages_status is not None:
                self.messages_status.color = COLORS["warning"]
                self.messages_status.text = "Введи сообщение."
            return
        try:
            send_friend_message(viewer.email, target.email, text)
        except ValueError as error:
            if self.messages_status is not None:
                self.messages_status.color = COLORS["warning"]
                self.messages_status.text = str(error)
            return

        self.messages_input.text = ""
        if self.messages_status is not None:
            self.messages_status.color = COLORS["success"]
            self.messages_status.text = "Отправлено."
        self._refresh_messages_popup()

    def _clear_messages_popup_refs(self):
        self.messages_popup = None
        self.messages_box = None
        self.messages_scroll = None
        self.messages_input = None
        self.messages_status = None

    def _dismiss_messages_popup(self):
        if self.messages_popup is not None:
            popup = self.messages_popup
            self._clear_messages_popup_refs()
            popup.dismiss()

    def _go_back(self, *_):
        target_screen = self.return_screen if self.return_screen in getattr(self.manager, "screen_names", []) else "start"
        self.manager.current = target_screen
