from kivy.app import App
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen

from ui import AppButton, AppTextInput, BodyLabel, BrandTitle, COLORS, PixelLabel, RoundedPanel, ScreenBackground, build_scrollable_content, register_game_font


class CreateRoomScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        register_game_font()

        root = ScreenBackground()
        scroll, content = build_scrollable_content()

        back_btn = AppButton(text="Назад", compact=True, size_hint_x=None, width=dp(132))
        back_btn.bind(on_release=lambda *_: setattr(self.manager, "current", "start"))
        content.add_widget(back_btn)
        content.add_widget(BrandTitle(text="ALIAS ONLINE", height=dp(136), font_size=sp(44), shadow_step=dp(3)))
        content.add_widget(PixelLabel(text="Создать комнату", font_size=sp(20), center=True))

        intro = RoundedPanel(
            orientation="vertical",
            padding=[dp(18), dp(18), dp(18), dp(18)],
            spacing=dp(10),
            size_hint_y=None,
        )
        intro.bind(minimum_height=intro.setter("height"))
        intro.add_widget(
            BodyLabel(
                center=True,
                text="Здесь будет настройка онлайн-лобби для будущей серверной части.",
            )
        )
        intro.add_widget(
            BodyLabel(
                center=True,
                color=COLORS["warning"],
                text="Имя игрока теперь берется из текущей сессии: из профиля или из гостевого режима.",
            )
        )
        content.add_widget(intro)

        form_card = RoundedPanel(
            orientation="vertical",
            padding=[dp(16), dp(16), dp(16), dp(16)],
            spacing=dp(12),
            size_hint_y=None,
        )
        form_card.bind(minimum_height=form_card.setter("height"))
        form_card.add_widget(PixelLabel(text="Параметры комнаты", font_size=sp(12), center=True))
        form_card.add_widget(BodyLabel(text="Игрок"))
        self.profile_name_label = BodyLabel(
            color=COLORS["accent"],
            text="Имя будет подтянуто из текущей сессии.",
        )
        form_card.add_widget(self.profile_name_label)
        form_card.add_widget(BodyLabel(text="Название лобби"))
        self.room_name_input = AppTextInput(hint_text="Например, Вечерний Alias")
        form_card.add_widget(self.room_name_input)
        form_card.add_widget(
            BodyLabel(
                color=COLORS["text_muted"],
                text="Рекомендуемый стартовый набор: 6 раундов, 60 секунд на ход, приватная комната по коду.",
            )
        )
        content.add_widget(form_card)

        actions = BoxLayout(orientation="vertical", spacing=dp(12), size_hint_y=None)
        actions.bind(minimum_height=actions.setter("height"))
        create_btn = AppButton(text="Подготовить лобби")
        create_btn.bind(on_release=self.prepare_room)
        actions.add_widget(create_btn)
        self.status_label = BodyLabel(
            center=True,
            color=COLORS["text_muted"],
            text="Заполни название комнаты, и можно будет переходить к подключению сервера.",
        )
        actions.add_widget(self.status_label)
        content.add_widget(actions)

        root.add_widget(scroll)
        self.add_widget(root)

    def on_pre_enter(self, *_):
        app = App.get_running_app()
        player_name = app.resolve_player_name() if app is not None else None
        if not player_name:
            self.profile_name_label.color = COLORS["warning"]
            self.profile_name_label.text = "Сначала выбери вход, регистрацию или гостевой режим."
            return

        self.profile_name_label.color = COLORS["accent"]
        self.profile_name_label.text = f"Комната будет создана от имени: {player_name}"

    def prepare_room(self, *_):
        app = App.get_running_app()
        player_name = app.resolve_player_name() if app is not None else None
        room_name = self.room_name_input.text.strip()

        if not player_name:
            self.status_label.color = COLORS["error"]
            self.status_label.text = "Сначала начни сессию через вход, регистрацию или гостевой режим."
            return

        if not room_name:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Добавь название комнаты, чтобы друзьям было проще найти лобби."
            return

        self.status_label.color = COLORS["success"]
        self.status_label.text = f"Лобби '{room_name}' для игрока {player_name} подготовлено."
