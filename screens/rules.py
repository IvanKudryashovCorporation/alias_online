from kivy.metrics import dp, sp
from kivy.uix.screenmanager import Screen

from ui import AppButton, BodyLabel, BrandTitle, CoinBadge, COLORS, PixelLabel, RoundedPanel, ScreenBackground, build_scrollable_content, register_game_font

RULES = [
    "Соберите команды и выберите объясняющего на текущий раунд.",
    "Объясняющий описывает слово без однокоренных слов, перевода и прямых подсказок.",
    "Если слово угадано, команда получает очко и сразу переходит к следующему слову.",
    "Если команда говорит «пас», слово пропускается и ход продолжается по вашим правилам матча.",
    "Побеждает команда, которая набрала больше очков к концу всех раундов.",
]

ONLINE_NOTES = [
    "Перед матчем удобно синхронизировать язык словаря и длительность раунда.",
    "Хост комнаты должен видеть, кто подключился и готов ли каждый игрок.",
    "На мобильном экране правила лучше держать короткими и с прокруткой, чтобы они не ломались на маленьких дисплеях.",
]


class RulesScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        register_game_font()

        root = ScreenBackground()
        scroll, content = build_scrollable_content(spacing=18)

        back_btn = AppButton(text="Назад", compact=True, size_hint_x=None, width=dp(132))
        back_btn.bind(on_release=lambda *_: setattr(self.manager, "current", "start"))
        content.add_widget(back_btn)
        content.add_widget(BrandTitle(text="ALIAS ONLINE", height=dp(136), font_size=sp(44), shadow_step=dp(3)))
        content.add_widget(PixelLabel(text="Правила игры", font_size=sp(20), center=True))

        summary = RoundedPanel(
            orientation="vertical",
            padding=[dp(18), dp(18), dp(18), dp(18)],
            spacing=dp(10),
            size_hint_y=None,
        )
        summary.bind(minimum_height=summary.setter("height"))
        summary.add_widget(
            BodyLabel(
                center=True,
                text="Экран правил теперь прокручивается и нормально помещается на телефонах. Это важно для Android-сборки и разных диагоналей.",
            )
        )
        summary.add_widget(
            BodyLabel(
                center=True,
                color=COLORS["text_muted"],
                text="Ниже — короткая версия правил и заметки для онлайн-комнат.",
            )
        )
        content.add_widget(summary)

        rules_card = RoundedPanel(
            orientation="vertical",
            padding=[dp(16), dp(16), dp(16), dp(16)],
            spacing=dp(10),
            size_hint_y=None,
        )
        rules_card.bind(minimum_height=rules_card.setter("height"))
        rules_card.add_widget(PixelLabel(text="Базовые правила", font_size=sp(12), center=True))
        for index, rule in enumerate(RULES, start=1):
            rules_card.add_widget(BodyLabel(text=f"{index}. {rule}"))
        content.add_widget(rules_card)

        notes_card = RoundedPanel(
            orientation="vertical",
            padding=[dp(16), dp(16), dp(16), dp(16)],
            spacing=dp(10),
            size_hint_y=None,
        )
        notes_card.bind(minimum_height=notes_card.setter("height"))
        notes_card.add_widget(PixelLabel(text="Что важно для online", font_size=sp(12), center=True))
        for note in ONLINE_NOTES:
            notes_card.add_widget(BodyLabel(text=f"• {note}"))
        content.add_widget(notes_card)

        root.add_widget(scroll)
        self.coin_badge = CoinBadge(pos_hint={"right": 0.965, "top": 0.96})
        root.add_widget(self.coin_badge)
        self.add_widget(root)

    def on_pre_enter(self, *_):
        self.coin_badge.refresh_from_session()
