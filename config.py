"""
Centralized configuration for the entire Alias Online application.
All magic constants, timeouts, sizes, and credentials are managed here.
Supports environment variables with fallbacks.
"""

import os
from kivy.metrics import dp, sp


# ============================================================================
# ENVIRONMENT VARIABLES
# ============================================================================

def _env_int(key: str, default: int) -> int:
    """Get integer from environment variable with fallback."""
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


def _env_float(key: str, default: float) -> float:
    """Get float from environment variable with fallback."""
    try:
        return float(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


def _env_str(key: str, default: str) -> str:
    """Get string from environment variable with fallback."""
    return (os.environ.get(key, "") or "").strip() or default


def _env_bool(key: str, default: bool) -> bool:
    """Get boolean from environment variable with fallback."""
    val = (os.environ.get(key, "") or "").strip().lower()
    if val in {"true", "1", "yes", "on"}:
        return True
    if val in {"false", "0", "no", "off"}:
        return False
    return default


# ============================================================================
# UI LAYOUT CONSTANTS (dp = density-independent pixels)
# ============================================================================

# Button sizes
BUTTON_COMPACT_WIDTH = dp(122)
BUTTON_COMPACT_HEIGHT = dp(46)
BUTTON_NORMAL_WIDTH = dp(228)
BUTTON_NORMAL_HEIGHT = dp(46)
BUTTON_DANGER_WIDTH = dp(228)
BUTTON_DANGER_HEIGHT = dp(46)

# Icon sizes
ICON_SMALL = dp(22)
ICON_MEDIUM = dp(52)
ICON_LARGE = dp(88)

# Spacing and padding
SPACING_XS = dp(2)
SPACING_SM = dp(4)
SPACING_MD = dp(6)
SPACING_LG = dp(8)
SPACING_XL = dp(10)
SPACING_XXL = dp(12)

PADDING_SM = [dp(4), dp(4), dp(4), dp(4)]
PADDING_MD = [dp(8), dp(8), dp(8), dp(8)]
PADDING_LG = [dp(12), dp(8), dp(12), dp(8)]
PADDING_XL = [dp(16), dp(16), dp(16), dp(16)]

# Border radius
RADIUS_SMALL = dp(8)
RADIUS_MEDIUM = dp(14)
RADIUS_LARGE = dp(18)
RADIUS_XL = dp(22)
RADIUS_PANEL = dp(34)

# Line widths
BORDER_THIN = 1.0
BORDER_MEDIUM = 1.2
BORDER_THICK = 1.6
BORDER_BOLD = 2.2

# Height constants
HEADER_HEIGHT = dp(56)
STATUS_HEIGHT = dp(18)
CARD_HEIGHT_SMALL = dp(44)
CARD_HEIGHT_MEDIUM = dp(126)
CARD_HEIGHT_LARGE = dp(188)
MODAL_HEIGHT = dp(360)

# Screen-specific heights
ROOM_META_HEIGHT = dp(18)
BRAND_TITLE_HEIGHT = dp(72)
PLAYERS_WRAP_HEIGHT = dp(248)
PLAYERS_WRAP_ROUND_HEIGHT = dp(176)
PLAYERS_SUMMARY_HEIGHT = dp(22)
LOBBY_START_HEIGHT = dp(52)
PHASE_WRAP_HEIGHT = dp(62)
EXPLAINER_CARD_HEIGHT = dp(138)
WORD_STAGE_HEIGHT = dp(198)
WORD_CARD_HEIGHT = dp(188)
VOICE_CARD_HEIGHT = dp(0)
SCORES_WRAP_HEIGHT = dp(132)
SCORES_WRAP_OVERLAY_HEIGHT = dp(162)
CHAT_INPUT_HEIGHT = dp(48)
CHAT_HOST_HEIGHT = dp(210)

# Chat overlay heights (is_explainer, can_chat)
CHAT_OVERLAY_HEIGHT_EXPLAINER = dp(238)
CHAT_OVERLAY_HEIGHT_CAN_CHAT = dp(214)
CHAT_OVERLAY_HEIGHT_NO_CHAT = dp(182)
CHAT_OVERLAY_MIN_HEIGHT = dp(74)
CHAT_OVERLAY_MAX_HEIGHT = dp(232)

# Scroll bar width
SCROLLBAR_WIDTH = dp(4)

# Font sizes (sp = scale-independent pixels)
FONT_XS = sp(10)
FONT_SM = sp(11)
FONT_MD = sp(12)
FONT_LG = sp(14)
FONT_XL = sp(17)
FONT_HEADER = sp(20)
FONT_TITLE = sp(38)

# Chat-specific font sizes
CHAT_FONT_EXPLAINER = sp(10.2)
CHAT_FONT_NORMAL = sp(11.6)

# Player grid
MIN_COLUMN_WIDTH = dp(86)  # rounded mode
MIN_COLUMN_WIDTH_LOBBY = dp(110)  # lobby mode
GRID_SPACING = dp(8)
GRID_PADDING = dp(8)

# Mic button
MIC_BUTTON_SIZE = dp(84)
MIC_BUTTON_TOP_SIZE = dp(88)
MIC_GLOW_SIZE = dp(88)

# Word card
WORD_CARD_MIN_WIDTH = dp(220)
WORD_CARD_PADDING = dp(16)
WORD_CARD_Y_OFFSET = dp(6)

# Chat card overlay
CHAT_CARD_MIN_WIDTH = dp(280)
CHAT_CARD_MIN_WIDTH_SPEC = dp(300)
CHAT_CARD_MAX_WIDTH = dp(430)
CHAT_CARD_PADDING = dp(44)
CHAT_OVERLAY_MARGIN = dp(22)
CHAT_OVERLAY_WORD_OFFSET = dp(8)
CHAT_OVERLAY_SCORE_OFFSET = dp(14)

# Coin badge
COIN_BADGE_WIDTH = dp(116)
COIN_BADGE_HEIGHT = dp(46)


# ============================================================================
# TIMING & POLLING CONSTANTS
# ============================================================================

# Polling intervals - increased from 0.65s (aggressive) to 1.0s (balanced)
# This reduces server load and battery drain while maintaining responsive UX
POLLING_INTERVAL_SECONDS = _env_float("POLLING_INTERVAL_SECONDS", 1.0)
POLLING_TIMEOUT_SECONDS = 4.0

# Adaptive polling backoff: multiply interval by this factor on error
# e.g., 1.0s * 1.5 = 1.5s, then 1.5s * 1.5 = 2.25s (capped at 8s)
POLLING_ERROR_BACKOFF_FACTOR = 1.5
POLLING_MAX_BACKOFF_SECONDS = 8.0

# Countdown/round timers
COUNTDOWN_TIMER_INTERVAL = 0.1
ROUND_TIMER_INTERVAL = 0.1

# Voice/mic
VOICE_UI_SYNC_INTERVAL = 0.08
VOICE_PING_INTERVAL = 0.2
VOICE_PING_ACTIVE_DURATION = 3

# Watchdog for game start
GAME_START_WATCHDOG_TIMEOUT = 8.0

# Start attempt throttling
GAME_START_MIN_INTERVAL = _env_float("GAME_START_MIN_INTERVAL", 1.5)

# Mic haptic feedback cooldown
HAPTIC_COOLDOWN_SECONDS = 0.07

# Sound effect volume
CLICK_SOUND_VOLUME = 0.35


# ============================================================================
# NETWORK & RETRY CONSTANTS
# ============================================================================

# Room server URLs
DEFAULT_LOCAL_ROOM_SERVER_URL = "http://127.0.0.1:8765"
DEFAULT_PUBLIC_ROOM_SERVER_URL = "https://alias-online-eqqi.onrender.com"
REMOTE_WAKE_CACHE_TTL_SECONDS = 45
REMOTE_WAKE_TOTAL_TIMEOUT_SECONDS = 30
REMOTE_WAKE_PROBE_TIMEOUT_SECONDS = 12

# Retry configuration
REMOTE_GET_ATTEMPTS = 4
REMOTE_MUTATION_ATTEMPTS = 4
REMOTE_RETRY_BASE_DELAY_SECONDS = 0.55
RETRYABLE_HTTP_STATUSES = {408, 425, 429, 500, 502, 503, 504}

# SSL/TLS
DISABLE_SSL_VERIFY = _env_bool("DISABLE_SSL_VERIFY", False)


# ============================================================================
# EMAIL & AUTH CONSTANTS
# ============================================================================

# SMTP configuration (must be set via environment variables in production)
SMTP_HOST = _env_str("ALIAS_SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = _env_int("ALIAS_SMTP_PORT", 587)
SMTP_SSL_PORT = _env_int("ALIAS_SMTP_SSL_PORT", 465)
SMTP_SENDER_EMAIL = _env_str("ALIAS_SMTP_EMAIL", "aliasgameonline@gmail.com")
SMTP_APP_PASSWORD = os.environ.get("ALIAS_SMTP_APP_PASSWORD", "")  # Keep empty for safety
SMTP_TIMEOUT_SECONDS = _env_int("ALIAS_SMTP_TIMEOUT_SECONDS", 20)

# Email verification
EMAIL_CODE_TTL_SECONDS = _env_int("EMAIL_CODE_TTL_SECONDS", 600)  # 10 minutes
EMAIL_RESEND_COOLDOWN_SECONDS = _env_int("EMAIL_RESEND_COOLDOWN_SECONDS", 30)
EMAIL_MAX_ATTEMPTS = _env_int("EMAIL_MAX_ATTEMPTS", 5)

# Guest mode
GUEST_MAX_PER_ROOM = _env_int("GUEST_MAX_PER_ROOM", 4)


# ============================================================================
# GAME MECHANICS CONSTANTS
# ============================================================================

# Room creation cost in Alias Coins
ROOM_CREATION_COST = _env_int("ROOM_CREATION_COST", 5)

# Room exit penalty
ROOM_EXIT_PENALTY_COINS = _env_int("ROOM_EXIT_PENALTY_COINS", 50)
ROOM_EXIT_COOLDOWN_MINUTES = _env_int("ROOM_EXIT_COOLDOWN_MINUTES", 5)

# Message history limits
MESSAGE_HISTORY_MAX_SIZE = 180
DISPLAY_MESSAGES_ROUND = 22
DISPLAY_MESSAGES_LOBBY = 30
DISPLAY_MESSAGES_SIGNATURE_SIZE = 100

# Player grid limits
MAX_PLAYERS_DISPLAY = 12


# ============================================================================
# KIVY UI COLORS
# ============================================================================

COLORS = {
    # Text colors
    "text": (1, 1, 1, 1),
    "text_soft": (0.88, 0.92, 0.98, 1),
    "text_muted": (0.72, 0.8, 0.93, 1),

    # Accent and primary
    "accent": (0.99, 0.95, 0.36, 1),
    "button": (0.16, 0.43, 0.83, 0.95),
    "button_pressed": (0.13, 0.34, 0.68, 0.98),

    # Surfaces and backgrounds
    "surface": (0.06, 0.1, 0.17, 0.72),
    "surface_card": (0.07, 0.11, 0.18, 0.92),
    "surface_panel": (0.10, 0.15, 0.24, 0.90),
    "surface_strong": (0.05, 0.09, 0.15, 0.84),
    "surface_soft": (0.08, 0.12, 0.19, 0.62),
    "surface_chip": (0.11, 0.17, 0.27, 0.84),

    # Borders and overlays
    "outline": (1, 1, 1, 0.14),
    "outline_soft": (1, 1, 1, 0.08),
    "overlay": (0.03, 0.08, 0.12, 0.05),

    # Input fields
    "input_bg": (0.84, 0.89, 0.96, 1),
    "input_text": (0.04, 0.04, 0.05, 1),
    "input_readonly_bg": (0.89, 0.93, 0.98, 0.98),
    "input_readonly_text": (0.05, 0.08, 0.16, 1),
    "input_readonly_outline": (0.31, 0.48, 0.78, 0.34),

    # Status colors
    "success": (0.67, 1, 0.78, 1),
    "warning": (1, 0.89, 0.58, 1),
    "error": (1, 0.72, 0.72, 1),

    # Danger state
    "danger_button": (0.82, 0.23, 0.23, 0.96),
    "danger_button_pressed": (0.67, 0.16, 0.16, 0.98),

    # Avatar
    "avatar_placeholder_bg": (0.56, 0.61, 0.67, 0.96),
    "avatar_placeholder_text": (0.96, 0.97, 0.99, 1),

    # Scene backgrounds
    "lobby_sky": (0.39, 0.74, 0.95, 1),
    "game_sky": (0.24, 0.62, 0.93, 1),
    "scene_back_hill": (0.91, 0.95, 0.98, 0.70),
    "scene_front_hill": (0.97, 0.98, 1, 0.96),
    "scene_house_blue": (0.76, 0.88, 0.97, 0.98),
    "scene_house_cream": (0.98, 0.96, 0.87, 0.98),
    "scene_house_yellow": (0.98, 0.89, 0.49, 0.98),
    "scene_house_mint": (0.79, 0.92, 0.88, 0.98),
    "scene_roof": (0.98, 0.42, 0.20, 0.98),
    "scene_shadow": (0.15, 0.26, 0.38, 0.08),

    # Game stage
    "game_overlay": (0.03, 0.07, 0.12, 0.08),
    "game_stage": (0.12, 0.20, 0.32, 0.58),
    "game_stage_glow": (0.98, 0.82, 0.25, 0.24),
    "game_spotlight": (1, 0.98, 0.82, 0.16),

    # Game cards
    "game_card_blue": (0.28, 0.58, 0.92, 0.24),
    "game_card_gold": (0.98, 0.84, 0.28, 0.23),
    "game_card_cyan": (0.42, 0.88, 0.90, 0.22),
    "game_card_outline": (1, 1, 1, 0.11),

    # Game tokens
    "game_token_orange": (0.98, 0.50, 0.18, 0.28),
    "game_token_mint": (0.38, 0.92, 0.74, 0.24),
}


# ============================================================================
# DEBUGGING & LOGGING
# ============================================================================

DEBUG_MODE = _env_bool("DEBUG_MODE", False)
LOG_LEVEL = _env_str("LOG_LEVEL", "INFO")

# Redact sensitive info in logs
REDACT_TOKENS = _env_bool("REDACT_TOKENS", True)
REDACT_PASSWORDS = _env_bool("REDACT_PASSWORDS", True)
REDACT_EMAILS = _env_bool("REDACT_EMAILS", True)


