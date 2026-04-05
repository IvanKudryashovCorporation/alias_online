"""Tests for server-side pure functions and rate limiting."""
import sys
import os
import time
import unittest

# Add project root to path so we can import server modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from server.room_server import (
    COIN_REWARD_EXPLAINER,
    COIN_REWARD_GUESSER,
    WORDS,
    _difficulty_key,
    _normalize_guess,
    _normalize_player_name,
    _pick_word,
    _rate_limit_check,
    _RATE_LIMIT_BUCKETS,
    _required_players_to_start,
    _same_player_name,
    _is_bot_player,
)


class TestNormalizeGuess(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(_normalize_guess("Кот"), "кот")

    def test_strips_whitespace(self):
        self.assertEqual(_normalize_guess("  мяч  "), "мяч")

    def test_removes_punctuation(self):
        self.assertEqual(_normalize_guess("при-вет!"), "привет")

    def test_empty(self):
        self.assertEqual(_normalize_guess(""), "")
        self.assertEqual(_normalize_guess(None), "")


class TestNormalizePlayerName(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(_normalize_player_name("Ivan"), "ivan")

    def test_strips(self):
        self.assertEqual(_normalize_player_name("  Alex  "), "alex")

    def test_none(self):
        self.assertEqual(_normalize_player_name(None), "")


class TestSamePlayerName(unittest.TestCase):
    def test_same(self):
        self.assertTrue(_same_player_name("Ivan", "ivan"))
        self.assertTrue(_same_player_name(" Alex ", "Alex"))

    def test_different(self):
        self.assertFalse(_same_player_name("Ivan", "Alex"))

    def test_empty(self):
        self.assertFalse(_same_player_name("", ""))
        self.assertFalse(_same_player_name(None, None))


class TestDifficultyKey(unittest.TestCase):
    def test_easy_ru(self):
        self.assertEqual(_difficulty_key("легкая"), "easy")
        self.assertEqual(_difficulty_key("Легкая"), "easy")

    def test_easy_en(self):
        self.assertEqual(_difficulty_key("easy"), "easy")

    def test_medium(self):
        self.assertEqual(_difficulty_key("средняя"), "medium")
        self.assertEqual(_difficulty_key("medium"), "medium")

    def test_hard(self):
        self.assertEqual(_difficulty_key("сложная"), "hard")
        self.assertEqual(_difficulty_key("hard"), "hard")

    def test_mix(self):
        self.assertEqual(_difficulty_key(""), "mix")
        self.assertEqual(_difficulty_key("unknown"), "mix")


class TestPickWord(unittest.TestCase):
    def test_easy(self):
        word = _pick_word("easy")
        self.assertIn(word, WORDS["easy"])

    def test_medium(self):
        word = _pick_word("medium")
        self.assertIn(word, WORDS["medium"])

    def test_hard(self):
        word = _pick_word("hard")
        self.assertIn(word, WORDS["hard"])

    def test_mix(self):
        all_words = WORDS["easy"] + WORDS["medium"] + WORDS["hard"]
        word = _pick_word("")
        self.assertIn(word, all_words)


class TestRequiredPlayersToStart(unittest.TestCase):
    def test_always_two(self):
        self.assertEqual(_required_players_to_start(4), 2)
        self.assertEqual(_required_players_to_start(8), 2)
        self.assertEqual(_required_players_to_start(2), 2)


class TestCoinRewardConstants(unittest.TestCase):
    def test_guesser_reward(self):
        self.assertEqual(COIN_REWARD_GUESSER, 5)

    def test_explainer_reward(self):
        self.assertEqual(COIN_REWARD_EXPLAINER, 3)


class TestIsBotPlayer(unittest.TestCase):
    def test_regular_player(self):
        self.assertFalse(_is_bot_player("Ivan"))
        self.assertFalse(_is_bot_player("Гость1"))

    def test_empty(self):
        self.assertFalse(_is_bot_player(""))
        self.assertFalse(_is_bot_player(None))

    def test_bot_prefix(self):
        self.assertTrue(_is_bot_player("Bot Alex"))
        self.assertTrue(_is_bot_player("AI Player"))


class TestRateLimiting(unittest.TestCase):
    def setUp(self):
        _RATE_LIMIT_BUCKETS.clear()

    def test_allows_under_limit(self):
        for _ in range(5):
            self.assertTrue(_rate_limit_check("test_key", max_requests=5, window_seconds=60))

    def test_blocks_over_limit(self):
        for _ in range(5):
            _rate_limit_check("test_key2", max_requests=5, window_seconds=60)
        self.assertFalse(_rate_limit_check("test_key2", max_requests=5, window_seconds=60))

    def test_separate_keys(self):
        for _ in range(5):
            _rate_limit_check("key_a", max_requests=5, window_seconds=60)
        self.assertFalse(_rate_limit_check("key_a", max_requests=5, window_seconds=60))
        self.assertTrue(_rate_limit_check("key_b", max_requests=5, window_seconds=60))

    def test_window_expires(self):
        _rate_limit_check("expire_key", max_requests=1, window_seconds=0.1)
        self.assertFalse(_rate_limit_check("expire_key", max_requests=1, window_seconds=0.1))
        time.sleep(0.15)
        self.assertTrue(_rate_limit_check("expire_key", max_requests=1, window_seconds=0.1))


if __name__ == "__main__":
    unittest.main()
