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
| **1.2** | Registration eligibility | **Fixed:** Request/verify/confirm accept only inactive users with an empty password and no staff/superuser privileges. Established disabled accounts cannot register again. |
| **1.3** | Test cache & outbox isolation | **Fixed:** Reset locmem caches/outbox per test. Integration Redis resets only default-cache limiter keys and the separate session namespace within run-specific prefixes. |
| **1.4** | Issuance failure logging | **Fixed:** Log fixed operation messages and exception class names; never log raw issuance exceptions. Preserve required audit-service exception logging. |
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
| **P1.3** | PostgreSQL driver in production runtime | **Fixed:** Runtime/lock include `psycopg[binary]`. Production and integration tests use PostgreSQL; development/default tests use SQLite. |
| **P1.4** | Custom User Admin creation & change forms | **Fixed:** Implemented `CustomUserCreationForm` and `CustomUserChangeForm` in `core/admin.py` supporting `email` login and password hashing without `username` collisions. |
| **P1.5** | Admin session and user deactivation consistency | **Fixed:** Made `UserSessionAdmin` read-only in admin and routed deletes to `SessionService.deactivate_session`. Configured `UserAdmin.save_model` to invoke `SessionService.revoke_all_sessions(obj)` upon account deactivation (`is_active=False`). |
| **P2.1** | Clear auth cookies after password reset | **Fixed:** `PasswordResetConfirmView.post` applies `clear_auth_cookies(response)` to the HTTP 200 response upon successful password reset. |
| **P2.2** | Serialized matching-device login replacement | **Fixed:** `AuthService.login_user` locks the `user` row via `select_for_update()` under `transaction.atomic()` to serialize concurrent first logins from identical user/device/IP pairs. |
| **P2.3** | Atomic single-session revocation | **Fixed:** `deactivate_session` owns locking, blacklisting, deactivation, and on-commit cache invalidation. Logout uses stable session IDs; remove the duplicated access-JTI implementation. |
| **P3.3** | Purged unused `UserSession.location` | **Fixed:** Removed unused `location` field from `UserSession` in `core/models/user.py` and generated schema migration `0002_remove_usersession_location.py`. |

---

## 2. Security-Fix Execution

| Area | Implemented contract | Targeted validation |
| :--- | :--- | :--- |
| Authorization state | Lock users before code/session mutations; reject stale password/email/active snapshots; mint login tokens only after revalidation. | PostgreSQL state-change schedules, failed-attempt persistence, audit failure persistence. |
| Refresh reuse | Recheck blacklisted refresh reuse after concurrent rotation; revoke its active session. | Two concurrent refreshes; one success, one 401, final session inactive. |
| Purge | Lock candidate rows and recheck eligibility before deletion; retain self-deactivated users. | Reissue/confirmation after candidate selection; deletion failure rollback. |
| Recovery identity | Email change atomically removes old reset codes; reset issuance rechecks the locked address. | Old code rejection, new code acceptance, concurrent issuance/change, rollback. |
| Logout | Bind legacy tokens to their DB session ID in memory; revoke by stable ID through the shared service. | Modern/legacy tokens, both refresh/logout orders, missing/repeated session revocation, rollback/cache behavior. |
| Email identity | Normalize the whole address to lowercase; retain unique email and enforce `core_user_email_canonical`. Migration `0005` checks collisions before normalizing users and pending email-change addresses. Never merge accounts automatically. | All account flows, manager/admin writes, database bypass rejection, concurrent uniqueness, migration success/collision rollback. |
| Password input | Preserve leading/trailing spaces in all password fields; reject empty/whitespace-only values with native validation. | Admin login, registration/reset, email-change/self-deactivation reauthentication, existing weak/blank rules. |
| Production configuration | Reject malformed/negative proxy counts; set SMTP socket timeout to 10 seconds. | Synthetic settings only; actual mailer timeout wiring and bounded sanitized timeout retries. |
| Revoke-all | Fetch IDs of unexpired, not-yet-blacklisted tokens only; keep deactivation/cache invalidation atomic. | Expiry boundary, mixed token states, repeated revocation, insertion rollback, concurrent refresh, cache deletion. |
| Issuance logs | Log operation and exception class only; preserve response statuses and cleanup attempts. | Synthetic database/queue/cleanup exceptions containing email/password/code/token markers. |

- Run only explicitly authorized targeted tests; no final full-suite execution performed. Migration validation uses a disposable test database, not the supplied application database.
- CI provisions native PostgreSQL/Redis without Docker. `tests/settings_integration.py` uses local test credentials and isolated Redis prefixes; never run integration settings against production services.
- Production deployment, real SMTP delivery, and independent multi-process behavior remain unverified. Threaded Redis tests validate the shared backend, not a full worker topology.
- Apply migration `0005` only after reviewing possible identity collisions. On collision, resolve ownership manually and rerun; no automatic account deletion/merge.
- A database failure during queue-failure cleanup can leave a code until expiry; sanitized cleanup failure logs remain observable. Do not claim guaranteed cleanup while database writes are unavailable.

## 3. Open Items Outside This Fix Plan

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
- Behavioral tests exist for Feature 1, Feature 4b, and Feature 5a/5b. Current execution validated selected cases only; do not infer a current full-suite pass or production readiness.
