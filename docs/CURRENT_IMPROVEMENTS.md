# Current Improvements Backlog

> **Constraint:** Subordinate to [AGENTS.md](../AGENTS.md). Preserve security boundaries, URL order/names, response schemas, cookie semantics, CSRF enforcement, and one-time-code semantics.

---

## 1. Resolved Issues & Verified Fixes

| ID | Item | Resolution & Technical Disposition |
| :--- | :--- | :--- |
| **B1** | Password reset enumeration oracle | **Fixed:** Generic password validation runs in `PasswordResetConfirmSerializer` with `user=None`. User similarity validation executes inside `confirm_reset` only after one-time code verification succeeds, preventing account and name enumeration without a valid code. |
| **B2** | Throttle sequencing inversion | **Fixed:** `limit_code_requests` now checks and records the 2-second IP burst throttle before committing the 60-second email cooldown key. IP throttle rejection no longer consumes the user's email cooldown. |
| **B3** | Unhandled `IntegrityError` on concurrent email change | **Fixed:** `EmailChangeService.confirm_change` wraps `user.save()` with `try...except IntegrityError:`, returning HTTP 400 with `MSG_EMAIL_IN_USE` under race collisions. |
| **B4** | Non-deterministic session list order | **Fixed:** `SessionService.get_active_sessions_with_current` explicitly sorts sessions with `.order_by("-last_activity", "-created_at")`. |
| **B5** | Unnecessary exception in `get_client_ip` | **Fixed:** Checks for existence of non-empty `HTTP_X_FORWARDED_FOR` before splitting, avoiding `ValueError` exceptions on direct requests. |
| **B6** | Dead serializers & response messages | **Fixed:** Purged unreferenced serializers (`CodeIsInvalidSerializer`, `NewEmailAlreadyExistsSerializer`, `UserNotFoundSerializer`, `NoRefreshTokenProvidedSerializer`, `SessionRevokedOrInactiveSerializer`) and unused messages (`MSG_EMAIL_ALREADY_EXIST`, `MSG_USER_NOT_FOUND`). |
| **1.1** | Malformed JWT `session_id` | **Fixed:** Rejects non-positive/non-integer claims in `session_is_active` before ORM query; returns 401 instead of 500. |
| **1.2** | Active account registration verify | **Fixed:** Filters `user__is_active=False` in `RegistrationService.verify_code`. |
| **1.3** | Test cache & outbox isolation | **Fixed:** Clears default cache, session cache, and mail outbox in `BehaviorHelpers.setUp()`. |
| **1.4** | Infrastructure exception logging | **Fixed:** Added `logger.exception()` in `RegistrationService` and `EmailChangeService`. |
| **2.1** | Refresh JWT re-parsing | **Fixed:** Reads rotated access/refresh JTIs directly from in-memory token instances. |
| **2.2** | Authenticated token reuse | **Fixed:** Passes validated `request.auth` to session services; avoids re-parsing access cookies in protected views. |
| **2.3** | Revocation & login N+1 queries | **Fixed:** Uses `bulk_create(..., ignore_conflicts=True)` and batch updates for token blacklisting and session replacement. |
| **2.4** | Legacy cookie header mutation | **Reviewed:** Responses have no preexisting raw `Set-Cookie` header; Django emits `response.cookies` separately. Validated by contract tests. |
| **3.1** | Dead auth comments & flag | **Fixed:** Removed commented header auth branch and redundant `is_cookie_auth` variable. |
| **3.2** | Misspelled alias `MSG_PASWORD_RESET` | **Fixed:** Purged unused typo alias. |
| **3.3** | Empty permissions package | **Fixed:** Removed empty directory and initializer. |
| **3.4** | Canonical model exports | **Fixed:** `core.models` exports all models; satisfying cross-feature import boundaries. |

---

## 2. Open Items

### P1. Validate production secret key and database configuration

- In `app/settings/prod.py`, fail during startup if `SECRET_KEY` is missing or empty; do not defer failure to request handling.
- Replace the production SQLite configuration with a database that supports effective row-level locking (for example, PostgreSQL). Keep local development on SQLite.
- Preserve the documented settings contract and avoid logging secret values.
- Add focused checks for missing `SECRET_KEY` and production database engine/configuration. Do not claim concurrency safety based on SQLite.

### P1. Make reauthentication throttling atomic

- In `core/auth/rate_limit.py:require_current_password`, prevent concurrent requests from bypassing the five-failure limit.
- Use an atomic operation supported by the shared production cache for checking/incrementing the counter; retain fail-closed behavior on cache errors, existing response semantics, and successful-attempt reset.
- Add a focused test for concurrent or atomic counter behavior where the test backend can meaningfully exercise it; do not infer multi-worker behavior from locmem.

### P2. Require a password when creating a superuser

- In `core/models/user.py:UserManager.create_superuser`, reject `password=None` before creating the account.
- Preserve standard Django manager behavior and add a focused test that no user is created when the password is missing.

### P3. Remove stale development database comments

- Delete the commented-out database option list in `app/settings/dev.py`; it has no runtime effect and includes duplicates.
- Keep the actual SQLite development configuration unchanged.

### P3. Make `.env` loading intent explicit

- Review `python-dotenv` and `load_dotenv()` in `pyproject.toml` and `app/settings/base.py`.
- Decide and document whether automatic `.env` loading is required for local development. If it is, keep the dependency and limit loading to the development configuration; production must rely on injected settings and must not load an incidental `.env` file. If it is not required, remove the dependency and call.
- Do not inspect, print, or commit real environment values while making this change.
