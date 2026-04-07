# SMTP Password Setup Checklist

> ⚠️ **IMPORTANT**: The old SMTP password in `.env.local` was compromised and has been removed from the repository.

## ✅ Step 1: Generate New Gmail App Password

1. Go to https://myaccount.google.com/security
2. Ensure **2-Step Verification** is enabled
3. Navigate to **App passwords** (or find it via Settings > Security > App passwords)
4. Select:
   - **App**: Mail
   - **Device**: Windows Computer (or your device type)
5. Google will generate a **16-character password** with spaces: `abcd efgh ijkl mnop`
6. **Copy the password** (save it securely temporarily)

---

## ✅ Step 2: Add Secret to GitHub Actions

This secret will be used when building the APK.

1. Go to your GitHub repository
2. **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. **Name**: `ALIAS_SMTP_APP_PASSWORD`
5. **Secret**: Paste the 16-character password (remove spaces: `abcdefghijklmnop`)
6. Click **Add secret**

**Verification**: GitHub Actions can now access this secret when building the APK.

---

## ✅ Step 3: Add Environment Variable to Render

This variable will be used by the production server.

1. Go to https://dashboard.render.com/
2. Select your service: `alias-online-eqqi`
3. **Settings** → **Environment**
4. Click **Add Environment Variable**
5. **Key**: `ALIAS_SMTP_APP_PASSWORD`
6. **Value**: Paste the 16-character password (without spaces)
7. Click **Save Changes**

**Note**: Render will automatically restart the service with the new environment variable.

---

## ✅ Step 4: Add Secret to GitHub Secrets for Render Deployment

If you use GitHub Actions to deploy to Render, ensure the secret is passed:

1. In `.github/workflows/deploy.yml` (or similar), reference the secret:
   ```yaml
   - name: Deploy to Render
     env:
       ALIAS_SMTP_APP_PASSWORD: ${{ secrets.ALIAS_SMTP_APP_PASSWORD }}
   ```

---

## ✅ Step 5: Optional - Local Development

If you need to test email locally:

1. Create `.env.local` (it's in `.gitignore`, safe to create locally):
   ```bash
   export ALIAS_SMTP_APP_PASSWORD="your-16-char-password"
   export ALIAS_SMTP_EMAIL="aliasgameonline@gmail.com"
   ```

2. **Never commit** `.env.local` to git (it's in `.gitignore`)

3. Load it before running:
   ```bash
   source .env.local
   python main.py
   ```

---

## ✅ Step 6: Verify Configuration

To verify the SMTP configuration is correct, the code will:

1. Read `ALIAS_SMTP_APP_PASSWORD` from environment
2. Remove any spaces (Gmail passwords have spaces)
3. Connect to `smtp.gmail.com:587` with TLS
4. Authenticate using `aliasgameonline@gmail.com` and the password

**If email sending fails**, check:
- [ ] Environment variable `ALIAS_SMTP_APP_PASSWORD` is set
- [ ] Password is correct (compare with what Google showed)
- [ ] Gmail 2-Step Verification is enabled
- [ ] App password was generated (not account password)
- [ ] Check logs: `logger.error()` will show SMTP connection errors

---

## 📝 Variable Reference

| Variable | Purpose | Where to Set |
|----------|---------|--------------|
| `ALIAS_SMTP_APP_PASSWORD` | **REQUIRED**: Gmail app password | GitHub Secrets + Render Environment |
| `ALIAS_SMTP_EMAIL` | Sender email (default: aliasgameonline@gmail.com) | Optional, GitHub Secrets + Render |
| `ALIAS_SMTP_HOST` | SMTP server (default: smtp.gmail.com) | Optional, GitHub Secrets + Render |
| `ALIAS_SMTP_PORT` | SMTP port (default: 587) | Optional, GitHub Secrets + Render |
| `ALIAS_SMTP_TIMEOUT_SECONDS` | Connection timeout (default: 20) | Optional |

---

## 🔐 Security Notes

✅ **What's protected:**
- `.env.local` is in `.gitignore` → secrets never committed
- GitHub Secrets are encrypted and masked in logs
- Render environment variables are secure and masked
- Code only reads from environment variables (no hardcoded passwords)

⚠️ **Do NOT:**
- Share the password in messages or commits
- Use the account password (use app password only)
- Commit `.env.local` or `.env` files

---

## 🧪 Testing Email Sending

After setup, test email verification:

```python
# From Python shell on server
from services.email_verification import send_verification_email_async

send_verification_email_async(
    email="your-test-email@example.com",
    code="123456",
    callback=lambda success: print(f"Email sent: {success}")
)
```

Or check the app logs for email sending attempts.

---

**Setup Date**: 2026-04-07
**Status**: Ready for deployment
