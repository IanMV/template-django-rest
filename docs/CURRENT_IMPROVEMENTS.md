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

### P1. Preserve refresh-token reuse detection during concurrent refreshes

- In `SessionService.refresh_tokens`, a request parses its refresh token before taking the session lock. If two requests start together, the first can rotate the token; the second then finds no row with the old JTI and returns at the `not session` branch without calling `revoke_reused_refresh`.
- After serialization, detect whether the old token is now blacklisted and the same active session has a different refresh JTI; revoke that session as required by the reuse contract. Keep invalid-token responses indistinguishable.

### P1. Define and enforce one email identity policy

- Registration and email change store serializer input directly, while password reset and authentication perform exact email lookups. `EmailField` validation does not make the database identity case-insensitive; e.g. `Person@example.com` and `Person@EXAMPLE.COM` can create separate rows although delivery targets the same domain mailbox.
- Choose a canonicalization policy, apply it consistently to registration, login, reset, and email change, and enforce it in the database. Before migration, find and resolve existing collisions without merging accounts automatically.

### P2. Bound token-blacklist and stale-session storage

- `SessionService.revoke_all_sessions` iterates every `OutstandingToken` for a user, including expired tokens; no tracked code or workflow runs Simple JWT's expired-token cleanup. Token rows and blacklist work therefore grow with account lifetime and make later revocations slower.
- Add a scheduled/operational `flushexpiredtokens` cleanup and avoid blacklisting expired tokens. Also define cleanup for inactive-or-expired `UserSession` rows; expired refresh tokens currently leave rows marked active and visible in the session list indefinitely.

### P2. Validate production Redis and proxy settings

- `app/settings/prod.py` parses the Redis DB path but accepts unsupported or hostless `REDIS_URL` values; these can let startup succeed while cache operations fail at request time. Negative `NUM_PROXIES` values also silently disable forwarded-client-IP handling.
- Validate `REDIS_URL` scheme (`redis`/`rediss`) and hostname, and require `NUM_PROXIES >= 0` at startup. Do not add a Redis connectivity probe unless deployment requires fail-fast network checks.

### P3. Remove or correct stale response-message comments

- `core/shared/response_messages.py:3-4,18-19` says these constants are used by `response_serializers.py`, which does not exist in the tracked tree.
- Remove the stale comments or name the actual consumers (`views.py` and `core/shared/docs.py`).

### P3. Wire or remove the unused vulnerability-audit dependency

- `pip-audit` is in the `dev` dependency group, but no PDM script or CI workflow invokes it; `.github/workflows/ruff.yml` installs only the `lint` group.
- Add an explicit CI/script invocation if dependency auditing is intended now; otherwise remove the unused development dependency until that planned feature is implemented.

### Authorized feature status: audit and maintenance

- Feature 1 was already implemented before this change; keep standard absolute lifetime at 30 days until a reduction to 7 days receives explicit approval.
- Feature 5a/5b adds `AuditLog`, best-effort event recording, staff-only paginated `GET /api/audit/`, and no new Django admin. Database append-only permissions and any legal retention period remain undecided; do not claim tamper evidence or regulatory compliance.
- Feature 4b adds a single-Beat 03:00 cleanup task with bounded application-level batches. The stock Simple JWT `flushexpiredtokens` command itself is not batched. Audit retention defaults to disabled (`AUDIT_RETENTION_DAYS=None`) until a positive period is approved.
- Comprehensive behavioral tests implemented and passing across Feature 1, Feature 4b, and Feature 5a/5b (`tests/test_audit.py`, `tests/test_maintenance_purge.py`, `tests/test_remember_me.py`, `tests/test_async_email.py`). Covers authorization, rollback/failure persistence, sanitization, maintenance survival of self-deactivated accounts, and Celery beat scheduling.
