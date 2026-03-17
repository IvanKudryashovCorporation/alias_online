from kivy.app import App
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen

from ui import AppButton, AppTextInput, BodyLabel, BrandTitle, COLORS, PixelLabel, RoundedPanel, ScreenBackground, build_scrollable_content, register_game_font


class JoinRoomScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        register_game_font()

        root = ScreenBackground()
        scroll, content = build_scrollable_content()

        back_btn = AppButton(text="Назад", compact=True, size_hint_x=None, width=dp(132))
        back_btn.bind(on_release=lambda *_: setattr(self.manager, "current", "start"))
        content.add_widget(back_btn)
        content.add_widget(BrandTitle(text="ALIAS ONLINE", height=dp(136), font_size=sp(44), shadow_step=dp(3)))
        content.add_widget(PixelLabel(text="Войти в комнату", font_size=sp(20), center=True))

        info = RoundedPanel(
            orientation="vertical",
            padding=[dp(18), dp(18), dp(18), dp(18)],
            spacing=dp(10),
            size_hint_y=None,
        )
        info.bind(minimum_height=info.setter("height"))
        info.add_widget(
            BodyLabel(
                center=True,
                text="Экран готов к быстрому входу по коду комнаты.",
            )
        )
        info.add_widget(
            BodyLabel(
                center=True,
                color=COLORS["text_muted"],
                text="Имя игрока берется из текущей сессии: из профиля или из гостевого режима.",
            )
        )
        content.add_widget(info)

        form = RoundedPanel(
            orientation="vertical",
            padding=[dp(16), dp(16), dp(16), dp(16)],
            spacing=dp(12),
            size_hint_y=None,
        )
        form.bind(minimum_height=form.setter("height"))
        form.add_widget(PixelLabel(text="Данные игрока", font_size=sp(12), center=True))
        form.add_widget(BodyLabel(text="Игрок"))
        self.profile_name_label = BodyLabel(
            color=COLORS["accent"],
            text="Имя будет подтянуто из текущей сессии.",
        )
        form.add_widget(self.profile_name_label)
        form.add_widget(BodyLabel(text="Код комнаты"))
        self.room_code_input = AppTextInput(hint_text="Например, ALIAS7")
        form.add_widget(self.room_code_input)
        content.add_widget(form)

        actions = BoxLayout(orientation="vertical", spacing=dp(12), size_hint_y=None)
        actions.bind(minimum_height=actions.setter("height"))
        join_btn = AppButton(text="Проверить код")
        join_btn.bind(on_release=self.validate_room_code)
        actions.add_widget(join_btn)
        self.status_label = BodyLabel(
            center=True,
            color=COLORS["text_muted"],
            text="Код можно вводить коротким форматом 4-8 символов.",
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
        self.profile_name_label.text = f"Вход в комнату будет под именем: {player_name}"

    def validate_room_code(self, *_):
        app = App.get_running_app()
        player_name = app.resolve_player_name() if app is not None else None
        raw_code = self.room_code_input.text.strip().upper()
        code = "".join(character for character in raw_code if character.isalnum())

        self.room_code_input.text = code

        if not player_name:
            self.status_label.color = COLORS["error"]
            self.status_label.text = "Сначала начни сессию через вход, регистрацию или гостевой режим."
            return

        if len(code) < 4 or len(code) > 8:
            self.status_label.color = COLORS["warning"]
            self.status_label.text = "Код комнаты должен быть длиной от 4 до 8 символов без пробелов."
            return

        self.status_label.color = COLORS["success"]
        self.status_label.text = f"Код {code} выглядит корректно. Можно подключать комнату для {player_name}."
