# Current Improvements Backlog

> **Execution Directive for Autonomous AI Agents:**  
> Implement tasks strictly by priority (P1 -> P2 -> P3 -> P4). Preserve `AGENTS.md` boundaries: cookie-only auth, CSRF enforcement, URL names/order, response schemas, and `ATOMIC_REQUESTS=False`. Do NOT run `pdm run test` or `pdm run verify` autonomously; run only static checks (`pdm run lint`, `pdm run schema-check`, `pdm run migrations-check`) unless explicitly commanded by the user.

---

## Priority 1 (P1): Critical Bugs, Isolation Leaks & Error Handling

### Task 1.1: Guard `session_is_active` against Malformed `session_id` (Prevent HTTP 500)
- **Target:** `core/auth/session_cache.py:14-27`
- **Problem:** `token.get("session_id")` passed directly to `UserSession.objects.filter(pk=session_id)`. Non-integer or malformed payload (e.g. `"invalid"`, float) triggers unhandled `ValueError: Field 'id' expected a number`, returning HTTP 500 instead of HTTP 401 `AuthenticationFailed`.
- **Specification:**
  1. Validate `session_id` type: must be `int` and `session_id > 0`.
  2. If `session_id is not None` and invalid, immediately return `False`.
  3. Query `UserSession` only when `session_id` is a valid positive integer.
- **Verification:** Token with `{"session_id": "malformed"}` must return HTTP 401, not 500.

### Task 1.2: Enforce `user__is_active=False` in `RegistrationService.verify_code`
- **Target:** `core/registration/services.py:69-72`
- **Problem:** `verify_code` queries `EmailVerification.objects.filter(user__email=email)` without checking `user__is_active=False`. An active user with a lingering verification record gets HTTP 200 on verify, but fails on confirm (asymmetry with `confirm_registration` and `PasswordResetService`).
- **Specification:**
  Add `user__is_active=False` to `EmailVerification.objects.select_for_update().filter(user__email=email, user__is_active=False).first()`.
- **Verification:** Verification of a code for an existing active account must return HTTP 400 `MSG_CODE_INVALID`.

### Task 1.3: Eliminate Test Suite Cache & Mail Isolation Leak
- **Target:** `tests/base.py:14-17` and `tests/test_session_cache.py:13-16`
- **Problem:** `BehaviorHelpers.setUp()` calls only `cache.clear()` (default cache). `caches["sessions"]` is never cleared between tests in `ApiCase`. LocMemCache entries leak across test methods, creating false positives/negatives. `tests/test_session_cache.py` had to work around this with a custom `setUp`.
- **Specification:**
  1. In `tests/base.py:BehaviorHelpers.setUp`: call `cache.clear()`, `caches["sessions"].clear()`, and `mail.outbox.clear()`.
  2. In `tests/test_session_cache.py`: remove redundant `setUp` override.
- **Verification:** All tests inherit full cache and outbox isolation.

### Task 1.4: Add Infrastructure Exception Logging to One-Time-Code Services
- **Target:** `core/registration/services.py:62-63` and `core/email_change/services.py:45-46`
- **Problem:** `except Exception as exc: raise ServiceUnavailable() from exc` swallows database/SMTP infrastructure errors without logging. `logger` is unused in `RegistrationService` and unimported in `EmailChangeService`.
- **Specification:**
  1. In `core/registration/services.py`: log with `logger.exception("Registration code issuance failed")` before raising `ServiceUnavailable()`.
  2. In `core/email_change/services.py`: import `logging`, initialize `logger = logging.getLogger(__name__)`, and log with `logger.exception("Email change code issuance failed")`.
- **Verification:** Static lint passes; failed delivery logs stack trace.

---

## Priority 2 (P2): Logic Optimization, Concurrency & Redundancy

### Task 2.1: Eliminate Cryptographic JWT Re-parsing in `SessionService.refresh_tokens`
- **Target:** `core/auth/services.py:70-74`
- **Problem:** `new_refresh = RefreshToken(response_data["refresh"])` is already in memory. Calling `AccessToken(access)` and `RefreshToken(refresh)` re-runs full cryptographic HMAC-SHA256 signature verification and payload decoding.
- **Specification:**
  Extract JTIs directly from the in-memory tokens:
  ```python
  new_access_jti = str(new_refresh.access_token["jti"])
  new_refresh_jti = str(new_refresh["jti"])
  ```
- **Verification:** Token rotation updates `UserSession` with identical JTIs without redundant crypto passes.

### Task 2.2: Pass Authenticated Token Directly from Views to Services
- **Target:** `core/auth/session_views.py:49,68`, `core/auth/views.py:196`, `core/auth/services.py:109-152`
- **Problem:** Protected endpoints (`IsAuthenticated`) extract raw cookie string and call `AccessToken(raw_token)` again inside service methods, duplicating parsing and DB lookups.
- **Specification:**
  1. In `SessionService.deactivate_other_session`, `logout_user`, and `get_active_sessions_with_current`: accept `token=request.auth` (or pre-extracted `current_jti = str(request.auth["jti"])` and `current_session_id = request.auth.get("session_id")`).
  2. In `deactivate_other_session`: if `current_session_id == session_id`, immediately raise `ValidationError({"detail": MSG_CANNOT_DEACTIVATE_CURRENT_SESSION})` in O(1) without DB lookup.
- **Verification:** Deactivating current session returns 400; listing marks `current=True` accurately.

### Task 2.3: Batch Token Blacklisting & Session Inactivation (Eliminate N+1)
- **Target:** `core/auth/services.py:189-198` and `core/auth/services.py:239-260`
- **Problem:**
  1. `revoke_all_sessions` loops `for token in tokens: BlacklistedToken.objects.get_or_create(token=token)`, issuing up to 2*N queries.
  2. `AuthService.login_user` calls `deactivate_session` in a loop and potentially calls it again on `previous_session`.
- **Specification:**
  1. In `revoke_all_sessions`: use `BlacklistedToken.objects.bulk_create([BlacklistedToken(token=t) for t in tokens], ignore_conflicts=True)`.
  2. In `AuthService.login_user`: collect all session IDs to deactivate (`set(sessions) | ({previous_session} if previous_session else set())`), bulk update `is_active=False`, bulk blacklist their `refresh_jti` tokens, and call `invalidate_sessions(unique_session_ids)`.
- **Verification:** Session revocation and login replacement execute in O(1) queries.

### Task 2.4: Fix Header Mutation in `clear_legacy_refresh_cookie`
- **Target:** `core/auth/cookies.py:49-57`
- **Problem:** Instantiates a throwaway `HttpResponse()`, runs `delete_cookie`, and assigns `response["Set-Cookie"] = ...`, overwriting existing `Set-Cookie` headers instead of appending.
- **Specification:**
  Format Morsel directly using `SimpleCookie` and append via `response.headers.appendlist("Set-Cookie", cookie_output)`:
  ```python
  from http.cookies import SimpleCookie

  def clear_legacy_refresh_cookie(response):
      cookie = SimpleCookie()
      kwargs = get_auth_cookie_kwargs()
      cookie["refresh_token"] = ""
      cookie["refresh_token"]["path"] = "/"
      cookie["refresh_token"]["expires"] = "Thu, 01 Jan 1970 00:00:00 GMT"
      cookie["refresh_token"]["max-age"] = 0
      cookie["refresh_token"]["samesite"] = kwargs["samesite"]
      if kwargs["domain"]:
          cookie["refresh_token"]["domain"] = kwargs["domain"]
      if kwargs["secure"]:
          cookie["refresh_token"]["secure"] = True
      if kwargs["httponly"]:
          cookie["refresh_token"]["httponly"] = True
      response.headers.appendlist("Set-Cookie", cookie["refresh_token"].OutputString())
  ```
- **Verification:** Both refresh cookie expirations (`/api/refresh/` and `/`) are present in response headers without overriding.

---

## Priority 3 (P3): Dead Code & Model Registry Cleanup

### Task 3.1: Remove Commented Header Auth & Redundant Flag in `CustomAuthentication`
- **Target:** `core/auth/authenticate.py:37-62, 79`
- **Specification:**
  1. Delete lines 37-54 (18 lines of commented header auth code).
  2. Remove `is_cookie_auth` variable. Enforce CSRF directly: `if request.method not in ("GET", "HEAD", "OPTIONS"): enforce_csrf(request)`.
- **Verification:** `pdm run lint` passes; cookie CSRF enforcement remains intact.

### Task 3.2: Remove Typo Alias `MSG_PASWORD_RESET`
- **Target:** `core/shared/response_messages.py:10`
- **Specification:** Delete unused `MSG_PASWORD_RESET = MSG_PASSWORD_RESET`.
- **Verification:** `pdm run lint` passes; no references broken.

### Task 3.3: Delete Empty `core/shared/permissions/` Package
- **Target:** `core/shared/permissions/__init__.py`
- **Specification:** Delete empty directory and `__init__.py`.
- **Verification:** No import breaks.

### Task 3.4: Expose Canonical Models in `core/models/__init__.py`
- **Target:** `core/models/__init__.py`
- **Specification:**
  Export all models from package root to satisfy `AGENTS.md` import boundaries:
  ```python
  from core.models.email_change import EmailChange
  from core.models.email_verification import EmailVerification
  from core.models.one_time_code import OneTimeCode
  from core.models.password_reset import PasswordReset
  from core.models.user import User, UserSession

  __all__ = [
      "User",
      "UserSession",
      "OneTimeCode",
      "EmailVerification",
      "PasswordReset",
      "EmailChange",
  ]
  ```
- **Verification:** `from core.models import UserSession, EmailVerification` succeeds cleanly.

---

## Priority 4 (P4): Test Strictness & Edge Case Coverage

### Task 4.1: Add Strict Cookie Attribute Assertions in `tests/test_auth.py`
- **Target:** `tests/test_auth.py:30-38`
- **Specification:** Assert `path="/"`, `path="/api/refresh/"`, and `max-age` explicitly for `access_token` and `refresh_token` in `test_login_returns_detail_and_httponly_cookies`.
- **Verification:** Rejects regression if cookie paths are altered.

### Task 4.2: Add Malformed `session_id` JWT Test in `tests/test_session_cache.py`
- **Target:** `tests/test_session_cache.py`
- **Specification:** Add test issuing an access token with `token["session_id"] = "malformed_string"`. Assert that request to `/api/users/me/` returns HTTP 401, not HTTP 500.
- **Verification:** Verifies fix in Task 1.1.

### Task 4.3: Add Active Account Verification Test in `tests/test_registration.py`
- **Target:** `tests/test_registration.py`
- **Specification:** Add test verifying a registration code for an already active user. Assert it returns HTTP 400 `MSG_CODE_INVALID`.
- **Verification:** Verifies fix in Task 1.2.

### Task 4.4: Optimize Throttle Test Execution in `tests/test_rate_limit.py`
- **Target:** `tests/test_rate_limit.py:135-144`
- **Specification:**
  In `test_thirty_first_login_for_same_ip_is_throttled`: pre-seed cache key `login:ip:{ip_digest}` with count 30 instead of executing 30 sequential full HTTP POST requests with password hashing. Issue only the 31st request via client.
- **Verification:** Throttling behavior validated with >90% reduction in test execution time.
