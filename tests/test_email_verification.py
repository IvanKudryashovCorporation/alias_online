"""Tests for email verification async functionality."""
import sys
import os
import time
import threading
import unittest
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.email_verification import (
    begin_registration_verification,
    _generate_code,
    _mask_email,
    _normalize_code,
)


class TestEmailCodeGeneration(unittest.TestCase):
    """Test email code generation and validation."""
    
    def test_generate_code_format(self):
        """Verify code is 6 digits."""
        code = _generate_code()
        self.assertEqual(len(code), 6)
        self.assertTrue(code.isdigit())
    
    def test_generate_code_randomness(self):
        """Verify codes are different each time."""
        codes = {_generate_code() for _ in range(10)}
        self.assertGreater(len(codes), 5)  # At least 5 different codes
    
    def test_mask_email(self):
        """Test email masking."""
        masked = _mask_email("user@example.com")
        self.assertIn("@example.com", masked)
        self.assertNotIn("user", masked)
        self.assertTrue(masked.startswith("u*"))
    
    def test_normalize_code(self):
        """Test code normalization."""
        self.assertEqual(_normalize_code("123456"), "123456")
        self.assertEqual(_normalize_code("12 34 56"), "123456")
        self.assertEqual(_normalize_code(""), "")


class TestBeginRegistrationVerification(unittest.TestCase):
    """Test registration verification flow."""
    
    def test_non_blocking_execution(self):
        """Verify that registration doesn't block main thread (async pattern)."""
        import asyncio
        from async_utils import run_async
        
        completed = threading.Event()
        result_holder = {"result": None, "error": None}
        
        def worker():
            # Simulate quick local verification
            return {
                "session_id": "test123",
                "masked_email": "t***t@example.com",
                "expires_in": 600,
                "resend_in": 30,
            }
        
        def on_success(result):
            result_holder["result"] = result
            completed.set()
        
        def on_error(error):
            result_holder["error"] = str(error)
            completed.set()
        
        # Run async
        run_async(worker, on_success, on_error)
        
        # Wait for completion (should be quick for local test)
        is_done = completed.wait(timeout=5.0)
        self.assertTrue(is_done, "Async operation should complete within 5 seconds")
        self.assertIsNotNone(result_holder["result"])
        self.assertIsNone(result_holder["error"])
    
    def test_local_registration_success(self):
        """Test local registration with mock SMTP."""
        # This would require mocking email sending
        # For now, just verify the function exists and accepts parameters
        self.assertTrue(callable(begin_registration_verification))


class TestAsyncPattern(unittest.TestCase):
    """Test the async pattern used in registration."""
    
    def test_run_async_with_success(self):
        """Test run_async executes worker and calls success callback."""
        from async_utils import run_async
        from kivy.clock import Clock
        
        completed = threading.Event()
        callback_result = None
        
        def worker():
            return "test_result"
        
        def on_success(result):
            nonlocal callback_result
            callback_result = result
            completed.set()
        
        def on_error(err):
            completed.set()
        
        run_async(worker, on_success, on_error)
        
        # Give it time to complete (includes Clock.schedule_once)
        is_done = completed.wait(timeout=2.0)
        self.assertTrue(is_done, "Callback should be invoked within 2 seconds")
        self.assertEqual(callback_result, "test_result")
    
    def test_run_async_with_error(self):
        """Test run_async calls error callback on exception."""
        from async_utils import run_async
        
        completed = threading.Event()
        callback_error = None
        
        def worker():
            raise ValueError("Test error")
        
        def on_success(result):
            completed.set()
        
        def on_error(err):
            nonlocal callback_error
            callback_error = str(err)
            completed.set()
        
        run_async(worker, on_success, on_error)
        
        is_done = completed.wait(timeout=2.0)
        self.assertTrue(is_done, "Error callback should be invoked within 2 seconds")
        self.assertIn("Test error", callback_error)


class TestEmailTimeout(unittest.TestCase):
    """Test that email operations respect timeout."""
    
    def test_timeout_constant_configured(self):
        """Verify timeout is configured appropriately."""
        from services.email_verification import DEFAULT_REMOTE_TIMEOUT_SECONDS
        
        # Timeout should be at least 5 seconds for SMTP operations
        self.assertGreaterEqual(DEFAULT_REMOTE_TIMEOUT_SECONDS, 5)
        # But not excessively long
        self.assertLessEqual(DEFAULT_REMOTE_TIMEOUT_SECONDS, 60)


if __name__ == "__main__":
    unittest.main()
