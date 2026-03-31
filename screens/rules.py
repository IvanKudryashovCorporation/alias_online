from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from ui import (
    AppButton,
    BodyLabel,
    BrandTitle,
    PixelLabel,
    RoundedPanel,
    ScreenBackground,
    build_scrollable_content,
    register_game_font,
)


class RulesScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        register_game_font()

        root = ScreenBackground()
        scroll, content = build_scrollable_content(
            padding=[dp(18), dp(18), dp(18), dp(20)],
            spacing=12,
        )

        top_bar = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(50))
        back_btn = AppButton(text="Назад", compact=True, size_hint=(None, None), size=(dp(126), dp(46)))
        back_btn.bind(on_release=lambda *_: setattr(self.manager, "current", "start"))
        top_bar.add_widget(back_btn)
        top_bar.add_widget(Widget())
        content.add_widget(top_bar)

        content.add_widget(BrandTitle(text="ALIAS ONLINE", height=dp(136), font_size=sp(46), shadow_step=dp(3)))

        card = RoundedPanel(
            orientation="vertical",
            spacing=dp(10),
            padding=[dp(18), dp(16), dp(18), dp(16)],
            size_hint_y=None,
        )
        card.bind(minimum_height=card.setter("height"))
        card.add_widget(PixelLabel(text="Правила игры", font_size=sp(24), center=True, size_hint_y=None))

        blocks = [
            (
                "1. Кто объясняет",
                "Хост комнаты начинает матч и становится объясняющим. Он видит слово и говорит голосом, не печатая в чат.",
            ),
            (
                "2. Как угадывать",
                "Остальные игроки пишут догадки в текстовый чат. Если слово совпало, раундовое слово сразу меняется на следующее.",
            ),
            (
                "3. Очки за слово",
                "За верную догадку +1 получает объясняющий и +1 получает игрок, который угадал.",
            ),
            (
                "4. Скип карточки",
                "Если слово неудобно объяснять, смахни карточку в любую сторону. За скип начисляется -1.",
            ),
            (
                "5. Типы комнат",
                "Публичная комната видна всем в списке. Закрытая комната доступна только по коду приглашения.",
            ),
            (
                "6. Alias Coin",
                "Создание комнаты стоит 25 AC. Первый запуск игры в новом лобби бесплатный, каждый следующий запуск в этом же лобби — 25 AC.",
            ),
            (
                "7. Штраф за выход",
                "Если выйти из активного матча, действует штраф: -50 AC и временная блокировка входа/создания комнат.",
            ),
            (
                "8. Матчи подряд",
                "После окончания игры игроки остаются в комнате и могут сразу запустить следующий матч без пересоздания лобби.",
            ),
        ]
        for title, text in blocks:
            card.add_widget(PixelLabel(text=title, font_size=sp(15), center=False, size_hint_y=None))
            card.add_widget(
                BodyLabel(
                    text=text,
                    center=False,
                    font_size=sp(12),
                    size_hint_y=None,
                )
            )

        content.add_widget(card)
        content.add_widget(Widget(size_hint_y=None, height=dp(8)))

        root.add_widget(scroll)
        self.add_widget(root)
