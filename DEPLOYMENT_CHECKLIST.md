# Deployment Checklist - SMTP Security Update

**Date**: 2026-04-07
**Status**: ✅ Code fixes complete, awaiting credential setup

---

## 📋 Pre-Deployment Tasks

### Phase 1: Gmail Password Management (TODAY)

- [ ] **Revoke Old Password**
  - Go to https://myaccount.google.com/app-passwords
  - Find and delete the old app password (was in `.env.local`)
  - This prevents anyone from using the compromised password

- [ ] **Generate New Password**
  - Same URL: https://myaccount.google.com/app-passwords
  - Select: Mail + Windows Computer
  - Note: Google will show something like `abcd efgh ijkl mnop`
  - Copy the password (16 characters with spaces)

### Phase 2: GitHub Setup (TODAY)

- [ ] **Add GitHub Secret**
  - Go to repository Settings
  - Navigate to: **Secrets and variables** → **Actions**
  - Click: **New repository secret**
  - Name: `ALIAS_SMTP_APP_PASSWORD`
  - Value: Paste password without spaces (e.g., `abcdefghijklmnop`)
  - Click: **Add secret**

- [ ] **Verify GitHub Actions**
  - Go to **Actions** tab
  - Check that APK build workflow can access secrets
  - (It will automatically use `${{ secrets.ALIAS_SMTP_APP_PASSWORD }}`)

### Phase 3: Render Deployment (TODAY)

- [ ] **Add Environment Variable to Render**
  - Go to https://dashboard.render.com/
  - Select service: `alias-online-eqqi`
  - Go to: **Settings** → **Environment**
  - Click: **Add Environment Variable**
  - Key: `ALIAS_SMTP_APP_PASSWORD`
  - Value: Paste password (16 chars, no spaces)
  - Click: **Save Changes**

- [ ] **Verify Render Restart**
  - Render will automatically restart the service
  - Check the **Logs** tab to see startup messages
  - Should NOT see any SMTP password errors

### Phase 4: Local Testing (OPTIONAL, FOR DEV)

- [ ] **Create `.env.local` for testing** (if needed locally)
  - File: `.env.local`
  - Content: `export ALIAS_SMTP_APP_PASSWORD="your-password"`
  - Run: `source .env.local && python main.py`

- [ ] **Run verification script**
  ```bash
  python verify_smtp_config.py
  ```
  - Should show: ✅ All checks passed

---

## 🔍 Code Changes Verification

| File | Change | Status |
|------|--------|--------|
| `.env.local` | Removed from repo | ✅ Done |
| `.gitignore` | Already contains `.env.local` | ✅ Verified |
| `.env.example` | Created with safe defaults | ✅ Done |
| `config.py` | All vars use `ALIAS_*` prefix | ✅ Done |
| `api_client.py` | SSL logging added | ✅ Done |
| `main.py` | Exception logging added | ✅ Fixed syntax error |
| `services/email_verification.py` | Security comment added | ✅ Done |
| `server/room_server.py` | SMTP config updated | ✅ Done |
| `SECURITY_FIXES.md` | Documentation created | ✅ Done |
| `SMTP_SETUP.md` | Setup guide created | ✅ Done |
| `verify_smtp_config.py` | Verification tool created | ✅ Done |

---

## 🚀 Deployment Steps

### Step 1: Push code to GitHub
```bash
git add .
git commit -m "Security: Update SMTP config, remove credentials, add logging"
git push origin main
```

### Step 2: Monitor GitHub Actions
- Check **Actions** tab
- Build should complete without showing any SMTP passwords in logs
- (GitHub masks secrets in logs)

### Step 3: APK will use GitHub Secret
- When GitHub Actions builds APK
- It injects `ALIAS_SMTP_APP_PASSWORD` from secrets
- APK will have correct SMTP password at build time
- Mobile app will work for email verification

### Step 4: Server already has Render variable
- Render service continues running with updated environment
- No redeployment needed (already restarted when you added the env var)

### Step 5: Test email functionality
- In app, try email verification:
  - Register new account
  - Check email inbox
  - Verify code should arrive

---

## ✅ Post-Deployment Verification

### Automated Tests
```bash
# Check SMTP config (requires env var to be set)
python verify_smtp_config.py
```

Expected output:
```
✅ ALIAS_SMTP_APP_PASSWORD is set
✅ config.py loaded successfully
✅ .env.local not found (correct for production)
✅ .env.local is in .gitignore
All checks passed! Your SMTP configuration is secure.
```

### Manual Tests

1. **Register a new account**
   - Open app
   - Register with new email
   - Check email for verification code
   - Code should arrive within 1 minute

2. **Check server logs**
   - Render: Go to service **Logs**
   - Should see successful SMTP connections
   - Should NOT see authentication errors

3. **Check app logs** (if saved locally)
   - Look for SMTP connection messages
   - Should NOT see "ALIAS_SMTP_APP_PASSWORD not found"

---

## 🔐 Security Verification

After deployment, verify:

- [ ] Old password was revoked in Gmail
- [ ] No credentials in git history
  ```bash
  git log --all --pretty=format: --name-only | grep -E "\.env|password|credential"
  # Should return empty
  ```

- [ ] Environment variables are used
  ```bash
  grep -r "ALIAS_SMTP_APP_PASSWORD" code/ --exclude-dir=.git
  # Should only show environment variable READS, not credentials
  ```

- [ ] SSL fallback is logged
  ```bash
  grep -r "INSECURE: SSL" server/ services/ api_client.py
  # Should find the logging statements
  ```

---

## 📞 Troubleshooting

### Email verification fails
1. Check Render **Environment** tab has `ALIAS_SMTP_APP_PASSWORD`
2. Run `python verify_smtp_config.py` on server
3. Check Render **Logs** for SMTP errors
4. Verify Gmail account has 2-Step Verification enabled

### Password seems wrong
1. Double-check you copied the password from Gmail (all 16 chars)
2. Remove spaces when pasting into GitHub/Render
3. Generate a new app password if unsure

### APK build fails
1. Check GitHub **Actions** tab
2. Verify `ALIAS_SMTP_APP_PASSWORD` secret exists
3. Secrets are only available to authenticated builds
4. Try a new commit to trigger rebuild

---

## 📚 Documentation Files

After deployment, reference:
- **SMTP_SETUP.md** - Detailed setup instructions
- **SECURITY_FIXES.md** - What was fixed and why
- **verify_smtp_config.py** - Verification tool
- **This file (DEPLOYMENT_CHECKLIST.md)** - Deployment steps

---

## ✨ Summary of Security Improvements

| Issue | Before | After |
|-------|--------|-------|
| Credentials | In `.env.local` (exposed) | In GitHub Secrets + Render (secure) |
| Variable naming | Inconsistent (`SMTP_*` vs `ALIAS_SMTP_*`) | Consistent (`ALIAS_SMTP_*` everywhere) |
| SSL logging | Silent fallback | Logged with "INSECURE: SSL" tag |
| Exceptions | Bare `except Exception: pass` | Specific types logged |
| Config | Partially in code | All in environment variables |
| Audit trail | None for SSL fallback | Full logging for security events |

---

**Status**: Ready for deployment
**Next Action**: Complete Phase 1-3 above, then test email
**Questions**: See SMTP_SETUP.md and SECURITY_FIXES.md
