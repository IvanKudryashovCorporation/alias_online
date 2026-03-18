from pathlib import Path

from kivy.core.text import LabelBase
from kivy.metrics import dp

APP_DIR = Path(__file__).resolve().parents[1]
FONT_PATH = APP_DIR / "fonts" / "Nunito-Black.ttf"
BRAND_FONT_PATH = APP_DIR / "fonts" / "LilitaOne-Regular.ttf"
BACKGROUND_PATH = APP_DIR / "image" / "lobby_minimal.png"

COLORS = {
    "text": (1, 1, 1, 1),
    "text_soft": (0.88, 0.92, 0.98, 1),
    "text_muted": (0.72, 0.8, 0.93, 1),
    "accent": (0.99, 0.95, 0.36, 1),
    "button": (0.16, 0.43, 0.83, 0.95),
    "button_pressed": (0.13, 0.34, 0.68, 0.98),
    "surface": (0.06, 0.1, 0.17, 0.72),
    "surface_card": (0.07, 0.11, 0.18, 0.92),
    "surface_panel": (0.10, 0.15, 0.24, 0.90),
    "surface_strong": (0.05, 0.09, 0.15, 0.84),
    "avatar_placeholder_bg": (0.56, 0.61, 0.67, 0.96),
    "avatar_placeholder_text": (0.96, 0.97, 0.99, 1),
    "outline": (1, 1, 1, 0.14),
    "overlay": (0.04, 0.08, 0.12, 0.10),
    "input_bg": (0.92, 0.94, 0.97, 1),
    "input_text": (0.04, 0.04, 0.05, 1),
    "input_readonly_bg": (0.97, 0.98, 0.995, 0.98),
    "input_readonly_text": (0.05, 0.08, 0.16, 1),
    "input_readonly_outline": (0.31, 0.48, 0.78, 0.34),
    "success": (0.67, 1, 0.78, 1),
    "warning": (1, 0.89, 0.58, 1),
    "error": (1, 0.72, 0.72, 1),
    "danger_button": (0.82, 0.23, 0.23, 0.96),
    "danger_button_pressed": (0.67, 0.16, 0.16, 0.98),
    "scene_back_hill": (0.91, 0.95, 0.98, 0.70),
    "scene_front_hill": (0.97, 0.98, 1, 0.96),
    "scene_house_blue": (0.76, 0.88, 0.97, 0.98),
    "scene_house_cream": (0.98, 0.96, 0.87, 0.98),
    "scene_house_yellow": (0.98, 0.89, 0.49, 0.98),
    "scene_house_mint": (0.79, 0.92, 0.88, 0.98),
    "scene_roof": (0.98, 0.42, 0.20, 0.98),
    "scene_shadow": (0.15, 0.26, 0.38, 0.18),
    "game_overlay": (0.03, 0.07, 0.12, 0.22),
    "game_stage": (0.09, 0.14, 0.22, 0.82),
    "game_stage_glow": (0.98, 0.82, 0.25, 0.16),
    "game_spotlight": (1, 0.98, 0.82, 0.10),
    "game_card_blue": (0.28, 0.58, 0.92, 0.18),
    "game_card_gold": (0.98, 0.84, 0.28, 0.17),
    "game_card_cyan": (0.42, 0.88, 0.90, 0.15),
    "game_card_outline": (1, 1, 1, 0.11),
    "game_token_orange": (0.98, 0.50, 0.18, 0.22),
    "game_token_mint": (0.38, 0.92, 0.74, 0.18),
}

_FONT_REGISTERED = False


def register_game_font():
    global _FONT_REGISTERED

    if _FONT_REGISTERED:
        return

    LabelBase.register(name="GameFont", fn_regular=str(FONT_PATH))
    LabelBase.register(name="BrandFont", fn_regular=str(BRAND_FONT_PATH))
    LabelBase.register(
        name="Roboto",
        fn_regular=str(FONT_PATH),
        fn_bold=str(FONT_PATH),
        fn_italic=str(FONT_PATH),
        fn_bolditalic=str(FONT_PATH),
    )
    _FONT_REGISTERED = True


def radius(value=22):
    point = dp(value)
    return [point, point, point, point]
