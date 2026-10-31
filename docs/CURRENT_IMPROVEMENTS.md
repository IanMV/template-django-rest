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
| **P1.3** | PostgreSQL driver in production runtime | **Fixed:** Added `psycopg[binary]>=3.2.0` to `pyproject.toml` dependencies and locked in `pdm.lock`. Production runs PostgreSQL backend; development/tests stay on SQLite. |
| **P1.4** | Custom User Admin creation & change forms | **Fixed:** Implemented `CustomUserCreationForm` and `CustomUserChangeForm` in `core/admin.py` supporting `email` login and password hashing without `username` collisions. |
| **P1.5** | Admin session and user deactivation consistency | **Fixed:** Made `UserSessionAdmin` read-only in admin and routed deletes to `SessionService.deactivate_session`. Configured `UserAdmin.save_model` to invoke `SessionService.revoke_all_sessions(obj)` upon account deactivation (`is_active=False`). |
| **P2.1** | Clear auth cookies after password reset | **Fixed:** `PasswordResetConfirmView.post` applies `clear_auth_cookies(response)` to the HTTP 200 response upon successful password reset. |
| **P2.2** | Serialized matching-device login replacement | **Fixed:** `AuthService.login_user` locks the `user` row via `select_for_update()` under `transaction.atomic()` to serialize concurrent first logins from identical user/device/IP pairs. |
| **P2.3** | Atomic single-session revocation | **Fixed:** Wrapped `SessionService.deactivate_session` and `deactivate_session_by_access_jti` mutations in `transaction.atomic()`, ensuring token blacklisting and session deactivation commit atomically. |
| **P3.3** | Purged unused `UserSession.location` | **Fixed:** Removed unused `location` field from `UserSession` in `core/models/user.py` and generated schema migration `0002_remove_usersession_location.py`. |

---

## 2. Open Items

*No open backlog items.*

