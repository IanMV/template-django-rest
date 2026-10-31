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
| **P1.1** | Production `SECRET_KEY` & PostgreSQL validation | **Fixed:** `app/settings/prod.py` validates `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `DATABASE_URL`, and `REDIS_URL` during startup, raising `ImproperlyConfigured` if missing/invalid. Configured PostgreSQL engine for production row-level locking. Local development remains on SQLite. |
| **P1.2** | Atomic reauthentication throttling | **Fixed:** `core/auth/rate_limit.py:require_current_password` atomically increments and checks failure count via `cache.add`/`cache.incr`, raising `Throttled` (429) when failures exceed 5 to prevent concurrent race-condition bypass. |
| **P2** | Superuser password enforcement | **Fixed:** `core/models/user.py:UserManager.create_superuser` rejects `password=None` or empty strings before `_create_user`, preventing creation of passwordless superusers. |
| **P3.1** | Stale dev database comments | **Fixed:** Purged 34 commented-out database options from `app/settings/dev.py`. |
| **P3.2** | Explicit `.env` loading boundaries | **Fixed:** Isolated `load_dotenv()` strictly to `app/settings/dev.py`. Removed from `base.py`. Production relies exclusively on injected environment variables. |

---

## 2. Open Items

### P1. Add the PostgreSQL driver to production dependencies

- `app/settings/prod.py` configures `django.db.backends.postgresql`, but `pyproject.toml` and `pdm.lock` do not include `psycopg` or `psycopg2`.
- Add the supported PostgreSQL driver as a runtime dependency and lock it. A production deployment must be able to load the configured backend without relying on an undeclared, manually installed package.
- Keep SQLite for development and tests.

### P1. Make Django admin work with the custom user model

- `core/admin.py:16-101` subclasses Django's stock `UserAdmin` without custom add/change forms. The stock add form targets the built-in `username` field, which `core.models.user.User` does not have.
- Supply forms compatible with the email-based `User` model, preserving safe password hashing and the existing admin fields. Ensure staff can open and submit the add-user form.

### P1. Prevent admin edits from bypassing session revocation and cache invalidation

- `core/admin.py:217-219` registers `UserSessionAdmin` with the unrestricted default `ModelAdmin`; a staff user can edit or delete session rows without blacklisting refresh tokens or invalidating the positive session cache.
- Make session records read-only in admin, or route every mutation through `SessionService` so database state, refresh-token blacklist, and cache invalidation stay consistent.
- Also ensure admin deactivation of a `User` revokes that user's sessions. Do not leave active sessions that can become valid again if the account is reactivated.

### P2. Clear authentication cookies after a successful password reset

- `core/password_reset/views.py:137-148` revokes sessions but returns without expiring the browser's access and refresh cookies.
- Apply the existing `clear_auth_cookies` helper to the success response. Preserve the public reset response body/status and cookie path semantics.

### P2. Serialize matching-device login session replacement

- `core/auth/services.py:227-255` locks matching active session rows, then creates a replacement. If no matching row exists, two concurrent first logins have no row to lock and can both create active sessions for the same user/device/IP.
- Serialize this operation using a stable row lock (for example, the user row) or an equivalent database-enforced design. Preserve the current replacement behavior; review the database locking semantics and do not infer concurrency safety from SQLite.

### P2. Make single-session revocation atomic

- `SessionService.deactivate_session` and `deactivate_session_by_access_jti` may blacklist a refresh token and deactivate its session in separate autocommit transactions when called by logout or session deletion.
- Wrap each full revocation mutation in `transaction.atomic()` so a database failure cannot leave refresh-token and session state partially updated. Keep cache deletion on commit and preserve existing response behavior.

### P3. Remove or justify unused session location data

- `UserSession.location` in `core/models/user.py` has no application service or API reader/writer; the generic admin form's ability to edit it does not provide application behavior.
- Confirm there is no external consumer; if unused, remove it with a migration. If it is intentionally reserved for a documented feature, document that contract instead of silently retaining dead schema.
