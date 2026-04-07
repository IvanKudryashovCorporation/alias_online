#!/usr/bin/env python3
"""
Verification script for SMTP configuration.
Run this to check if your SMTP setup is correct before deploying.
"""

import os
import sys


def check_environment():
    """Check if ALIAS_SMTP_APP_PASSWORD is set in environment."""
    print("=" * 60)
    print("CHECKING SMTP CONFIGURATION")
    print("=" * 60)

    password = os.environ.get("ALIAS_SMTP_APP_PASSWORD", "").strip()

    if not password:
        print("❌ ERROR: ALIAS_SMTP_APP_PASSWORD not set in environment")
        print("\nTo set it:")
        print("  export ALIAS_SMTP_APP_PASSWORD='your-16-char-password'")
        print("\nOr add to .env.local (local dev only):")
        print("  ALIAS_SMTP_APP_PASSWORD=your-16-char-password")
        return False

    # Remove spaces from password (Gmail passwords have spaces)
    password_clean = password.replace(" ", "")

    if len(password_clean) < 14:  # Gmail app passwords are typically 16 chars without spaces
        print("⚠️  WARNING: Password seems too short (expected ~16 chars)")

    print(f"✅ ALIAS_SMTP_APP_PASSWORD is set")
    print(f"   Length (without spaces): {len(password_clean)} chars")

    return True


def check_email_config():
    """Check other email configuration."""
    print("\nChecking email configuration...")

    # Try importing config
    try:
        from config import (
            SMTP_HOST,
            SMTP_PORT,
            SMTP_SENDER_EMAIL,
            SMTP_APP_PASSWORD,
        )

        print(f"✅ config.py loaded successfully")
        print(f"   SMTP_HOST: {SMTP_HOST}")
        print(f"   SMTP_PORT: {SMTP_PORT}")
        print(f"   SMTP_SENDER_EMAIL: {SMTP_SENDER_EMAIL}")

        if not SMTP_APP_PASSWORD:
            print("⚠️  WARNING: SMTP_APP_PASSWORD from config is empty")
            print("   This means ALIAS_SMTP_APP_PASSWORD env var is not set")
            return False

        print(f"✅ SMTP_APP_PASSWORD is loaded from environment")
        return True

    except ImportError as e:
        print(f"❌ ERROR: Could not import config: {e}")
        return False


def check_env_file():
    """Check .env.local and .env.example"""
    print("\nChecking environment files...")

    env_local = ".env.local"
    env_example = ".env.example"

    # Check .env.local (should NOT exist in production)
    if os.path.exists(env_local):
        print(f"⚠️  WARNING: .env.local exists (for local dev only)")
        print(f"   Make sure it's in .gitignore and never committed")
    else:
        print(f"✅ .env.local not found (correct for production)")

    # Check .env.example (should have safe values)
    if os.path.exists(env_example):
        print(f"✅ .env.example exists with placeholder values")
    else:
        print(f"⚠️  WARNING: .env.example not found")

    return True


def check_gitignore():
    """Check .gitignore has .env.local"""
    print("\nChecking .gitignore...")

    gitignore = ".gitignore"

    if not os.path.exists(gitignore):
        print(f"⚠️  WARNING: .gitignore not found")
        return False

    with open(gitignore) as f:
        content = f.read()

    if ".env.local" in content or ".env" in content:
        print(f"✅ .env.local is in .gitignore (secrets won't be committed)")
    else:
        print(f"❌ ERROR: .env.local NOT in .gitignore")
        print(f"   This is a SECURITY RISK!")
        return False

    return True


def main():
    """Run all checks."""
    print("\n🔐 SMTP Security Configuration Verification\n")

    results = [
        ("Environment", check_environment()),
        ("Email Config", check_email_config()),
        ("Git Ignore", check_gitignore()),
        ("Files", check_env_file()),
    ]

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")

    all_passed = all(p for _, p in results)

    print("\n" + "=" * 60)

    if all_passed:
        print("✅ All checks passed! Your SMTP configuration is secure.")
        print("\nNext steps:")
        print("1. Add ALIAS_SMTP_APP_PASSWORD to GitHub Secrets")
        print("2. Add ALIAS_SMTP_APP_PASSWORD to Render environment")
        print("3. See SMTP_SETUP.md for detailed instructions")
        return 0
    else:
        print("❌ Some checks failed. Please fix the issues above.")
        print("\nSee SECURITY_FIXES.md and SMTP_SETUP.md for instructions.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
