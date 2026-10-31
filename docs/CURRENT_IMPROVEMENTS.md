# Current Application Improvements & Security Hardening

> **Target Audience:** Autonomous AI coding agents & refactoring harnesses.  
> **Repository:** `template-django-rest`  
> **Core Constraint:** Subordinate to [AGENTS.md](../AGENTS.md). Never break public REST contracts, CSRF requirements, HttpOnly cookie semantics, or assertions in `tests/test_contracts.py`.

---

## 1. Execution Directives for AI Agents

1. **Atomic Commits:** Implement one task (or cohesive batch) per commit with conventional prefixes (`fix:`, `refactor:`, `sec:`, `test:`, `perf:`).
2. **Contract Invariance:** Preserve response status codes, payload shapes, headers, and cookie flags (`HttpOnly`, `SameSite=Lax`, `Secure`).
3. **Verification Policy:** Run verification commands only when explicitly requested by user:
   ```bash
   SECRET_KEY=12345678901234567890123456789012345678901234567890 pdm run verify
   ```
4. **Model Location:** All Django ORM entities belong exclusively in `core/models/`.

---

## 2. Action Items Matrix

Status on this branch (items not marked done remain open):

| Status | Items | Decision |
| :--- | :--- | :--- |
| Done | `SEC-04`, `DEV-01`, `BUG-01`, `CLEAN-01`–`CLEAN-04`, `I18N-01` | Implemented without changing public responses. |
| Partial | `SEC-06` | Row-lock verify attempts; keep 429 verification throttle open because it changes documented responses. Verify effective locking on production DB. |
| Blocked | `SEC-01` | Pre-existing uncommitted MD5 setting in `app/settings/base.py`; do not overwrite user changes. Production hash security remains at risk until removed. |
| Contract change | `SEC-02`, `SEC-03`, `SEC-05` | Require explicit authorization to change list status/shape, cookie path, or registration response respectively. |
| Design review | `ARCH-01`, `PROD-01`, `NET-01` | Preserve mail failure rollback/503; provision Redis before cache switch; define trusted proxy boundary before honoring forwarded headers. Existing mail dispatch inside transactions remains unresolved. |

Do not execute the historical batch verification commands below unless the user explicitly requests tests or verification. The detailed specs below are proposals, not overrides of `AGENTS.md`.

| ID | Priority | Scope | Category | Complexity |
| :--- | :--- | :--- | :--- | :--- |
| `SEC-01` | **P0 (Critical)** | `app/settings/base.py`, `tests/base.py` | Crypto / Config | Low |
| `SEC-02` | **P0 (Critical)** | `core/users/{views,services}.py`, tests | Auth / PII Leak | Low |
| `SEC-03` | **P1 (High)** | `core/auth/cookies.py`, tests | Cookie Security | Low |
| `SEC-04` | **P1 (High)** | `core/auth/{rate_limit,services}.py` | DoS Resilience | Medium |
| `SEC-05` | **P1 (High)** | `core/registration/{views,services}.py` | Privacy / Anti-Enum | Low |
| `SEC-06` | **P1 (High)** | `core/{registration,password_reset,email_change}/services.py` | Concurrency / Brute-Force | Medium |
| `ARCH-01`| **P1 (High)** | `core/*/services.py`, `tests/base.py` | Concurrency / Test Harness | Medium |
| `PROD-01`| **P1 (High)** | `app/settings/prod.py` | Django 6.1 / Deploy | Medium |
| `BUG-01` | **P2 (Medium)** | `core/password_reset/views.py`, `core/shared/*` | Typo / Consistency | Low |
| `NET-01` | **P2 (Medium)** | `core/auth/rate_limit.py`, `app/settings/base.py` | Network / Proxy | Medium |
| `DEV-01` | **P2 (Medium)** | `app/settings/dev.py` | DX / Stability | Low |
| `CLEAN-01`| **P3 (Low)** | `core/shared/permissions/is_user.py` | Dead Code | Low |
| `CLEAN-02`| **P3 (Low)** | `core/shared/email_token_sender.py` | Clean Code | Low |
| `CLEAN-03`| **P3 (Low)** | `core/models/user.py` | PEP 8 Imports | Low |
| `CLEAN-04`| **P3 (Low)** | `core/models/email_change.py` | Docstring | Low |
| `I18N-01` | **P3 (Low)** | `core/email_change/services.py` | i18n / Constants | Low |

---

## 3. Detailed Technical Specifications

---

### `SEC-01`: Remove Global MD5 Hasher & Scope Fast Hasher to Test Runner

- **Target Files:**
  - `app/settings/base.py`
  - `tests/base.py`
- **Root Cause:** `PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]` was appended to `app/settings/base.py`, degrading production and dev hash security. `tests/base.py` lacked test-scoped hasher and 32+ byte `SECRET_KEY`, triggering `InsecureKeyLengthWarning`.
- **Implementation:**
  1. Remove `PASSWORD_HASHERS` completely from `app/settings/base.py`.
  2. In `tests/base.py`, append `PASSWORD_HASHERS` and a 50-byte `SECRET_KEY` to the `@override_settings` decorator on `ApiCase` and `ApiTransactionCase`:
     ```python
     @override_settings(
         MAILERS={"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}},
         PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
         SECRET_KEY="django-insecure-test-key-with-strictly-more-than-thirty-two-bytes-12345",
     )
     class ApiCase(BehaviorHelpers, TestCase):
         pass
     ```
- **Verification Command:** `pdm run test` (suite must finish in <3s with 0 warnings).

---

### `SEC-02`: Restrict User Directory Listing to Staff & Add Pagination

- **Target Files:**
  - `core/users/views.py`
  - `core/users/services.py`
  - `tests/test_users.py`
  - `tests/test_contracts.py`
- **Root Cause:** `GET /api/users/list/` returned all active users (UUID, name, email) to any regular authenticated user with no pagination, violating LGPD Art. 6 and enabling OOM DoS scraping.
- **Implementation:**
  1. In `core/users/views.py`:
     - Change permission: `permission_classes = [IsAdminUser]`.
     - Enable pagination: `pagination_class = PageNumberPagination`.
  2. In `core/users/services.py`:
     ```python
     @staticmethod
     def list_users(requesting_user: User):
         if not (requesting_user.is_staff or requesting_user.is_superuser):
             raise PermissionDenied()
         return User.objects.all().order_by("-created_at")
     ```
  3. In `tests/test_users.py`:
     - Assert regular users (`is_staff=False`) get `403 Forbidden`.
     - Assert staff users (`is_staff=True`) receive the paginated list.
- **Verification Command:** `pdm run schema-check && pdm run test tests.test_users tests.test_contracts`.

---

### `SEC-03`: Isolate Refresh Token Cookie Path to `/api/refresh/`

- **Target Files:**
  - `core/auth/cookies.py`
  - `tests/test_auth.py`
  - `tests/test_contracts.py`
- **Root Cause:** `refresh_token` cookie was issued with `path="/"`. Browsers transmitted long-lived refresh credentials on every request, expanding header leakage exposure to proxy logs and WAFs.
- **Implementation:**
  1. In `core/auth/cookies.py`:
     ```python
     def get_auth_cookie_kwargs(is_refresh=False):
         lifetime = (
             settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]
             if is_refresh
             else settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"]
         )
         cookie_path = (
             settings.SIMPLE_JWT.get("REFRESH_COOKIE_PATH", "/api/refresh/")
             if is_refresh
             else settings.SIMPLE_JWT.get("AUTH_COOKIE_PATH", "/")
         )
         return {
             "max_age": int(lifetime.total_seconds()),
             "httponly": settings.SIMPLE_JWT.get("AUTH_COOKIE_HTTP_ONLY", True),
             "secure": settings.SIMPLE_JWT.get("AUTH_COOKIE_SECURE", False),
             "domain": settings.SIMPLE_JWT.get("AUTH_COOKIE_DOMAIN"),
             "path": cookie_path,
             "samesite": settings.SIMPLE_JWT.get("AUTH_COOKIE_SAMESITE", "Lax"),
         }
     ```
  2. In `clear_auth_cookies(response)`:
     - Delete `access_token` using path `"/"`.
     - Delete `refresh_token` using path `"/api/refresh/"`.
  3. Update cookie path assertions in `tests/test_contracts.py`.
- **Verification Command:** `pdm run test tests.test_auth tests.test_contracts`.

---

### `SEC-04`: Mitigate Distributed Account DoS in Login Rate Limiting

- **Target Files:**
  - `core/auth/rate_limit.py`
  - `core/auth/services.py`
  - `tests/test_rate_limit.py`
- **Root Cause:** `limit_login_attempts` throttled by `login:email:{hash}` globally (10 attempts / 5 min) before credential verification. An attacker spraying invalid passwords via rotating proxies locked victims out indefinitely (Account DoS). Successful logins never cleared attempts.
- **Implementation:**
  1. In `core/auth/rate_limit.py`:
     ```python
     def limit_login_attempts(email: str, ip_address: str | None) -> None:
         email_digest = hashlib.sha256(email.strip().casefold().encode()).hexdigest()
         keys = []

         # 1. Global IP throttling: max 30 attempts per IP / 5 min
         if ip_address:
             ip_digest = hashlib.sha256(ip_address.encode()).hexdigest()
             keys.append((f"login:ip:{ip_digest}", 30, 300))

         # 2. IP + Email tuple: max 10 attempts per specific tuple / 5 min
         if ip_address:
             pair_digest = hashlib.sha256(f"{ip_address}:{email_digest}".encode()).hexdigest()
             keys.append((f"login:pair:{pair_digest}", 10, 300))

         for key, maximum, timeout in keys:
             if cache.add(key, 1, timeout=timeout):
                 continue
             try:
                 attempts = cache.incr(key)
             except ValueError:
                 cache.add(key, 1, timeout=timeout)
                 continue
             if attempts > maximum:
                 raise Throttled(wait=timeout)
     ```
  2. Add cleanup function:
     ```python
     def reset_login_attempts(email: str, ip_address: str | None) -> None:
         if not ip_address:
             return
         email_digest = hashlib.sha256(email.strip().casefold().encode()).hexdigest()
         pair_digest = hashlib.sha256(f"{ip_address}:{email_digest}".encode()).hexdigest()
         cache.delete(f"login:pair:{pair_digest}")
     ```
  3. In `AuthService.login_user`: Call `reset_login_attempts(email, ip_address)` upon successful authentication.
- **Verification Command:** `pdm run test tests.test_rate_limit tests.test_auth`.

---

### `SEC-05`: Eliminate Account Enumeration in Registration Flow

- **Target Files:**
  - `core/registration/services.py`
  - `core/registration/views.py`
  - `tests/test_registration.py`
- **Root Cause:** `RegistrationRequestView` returned HTTP 400 `{"email": ["This account is already active."]}` when an active user existed, allowing attackers to harvest registered emails.
- **Implementation:**
  1. In `RegistrationService.request_registration`:
     - If user exists and `is_active=True`, do not raise `ValidationError`.
     - Dispatch security notification email via `transaction.on_commit()`: *"Registration attempt on existing account. If this was you, please log in or reset your password."*
     - Return normally.
  2. In `RegistrationRequestView`: Always respond HTTP 201 `{"detail": MSG_CODE_SENT}` uniformly.
  3. Update `tests/test_registration.py` assertions.
- **Verification Command:** `pdm run schema-check && pdm run test tests.test_registration`.

---

### `SEC-06`: Concurrency Locking & Rate Limiting for Code Verification

- **Target Files:**
  - `core/{registration,password_reset,email_change}/services.py`
  - `core/auth/rate_limit.py`
- **Root Cause:** Code verification (`verify_code`) checked attempts without row-level locks, allowing burst parallel requests to bypass the 5-attempt brute-force limit.
- **Implementation:**
  1. In `core/auth/rate_limit.py`, add verification rate limiter:
     ```python
     def limit_code_verification_attempts(ip_address: str | None) -> None:
         if not ip_address:
             return
         ip_digest = hashlib.sha256(ip_address.encode()).hexdigest()
         key = f"code-verify:ip:{ip_digest}"
         if cache.add(key, 1, timeout=60):
             return
         try:
             attempts = cache.incr(key)
         except ValueError:
             cache.add(key, 1, timeout=60)
             return
         if attempts > 15:
             raise Throttled(wait=60)
     ```
  2. In `verify_code()` methods, enforce `transaction.atomic()` with `select_for_update()`:
     ```python
     with transaction.atomic():
         verification = (
             EmailVerification.objects.select_for_update()
             .filter(user__email=email)
             .first()
         )
         if not verification or not verification.verify(code):
             raise serializers.ValidationError({"code": MSG_CODE_INVALID})
     ```
- **Verification Command:** `pdm run test tests.test_registration tests.test_password_reset tests.test_email_change`.

---

### `ARCH-01`: Decouple Email Dispatch via `on_commit` with Test Harness Support

- **Target Files:**
  - `core/{registration,password_reset,email_change}/services.py`
  - `tests/base.py`
- **Root Cause:** Synchronous `send_email_token` inside atomic blocks caused DB connection saturation. Moving directly to `transaction.on_commit()` broke `TestCase` tests because rolled-back test transactions suppress callbacks.
- **Implementation:**
  1. In service methods, wrap outbound mail dispatch:
     ```python
     with transaction.atomic():
         # DB writes...
         transaction.on_commit(lambda: send_email_token(user.email, raw_code, "Subject"))
     ```
  2. In `tests/base.py` (`BehaviorHelpers`), wrap mutating client helper calls with `self.captureOnCommitCallbacks(execute=True)` so callbacks run during test execution:
     ```python
     def email_code(self):
         self.assertTrue(mail.outbox)
         code = re.search(r"(?<!\d)\d{6}(?!\d)", mail.outbox[-1].body)
         self.assertIsNotNone(code)
         return code.group()
     ```
- **Verification Command:** `pdm run test tests.test_registration tests.test_password_reset tests.test_email_change`.

---

### `PROD-01`: Configure Django 6.1 Unified Mailers, Redis Cache & HTTPS Headers

- **Target Files:**
  - `app/settings/prod.py`
- **Root Cause:** Django 6.1 unified `MAILERS` requires backend connection options nested inside `"OPTIONS"`. Flat top-level keys are ignored, defaulting SMTP to unauthenticated `localhost:25`.
- **Implementation:**
  In `app/settings/prod.py`:
  ```python
  CACHES = {
      "default": {
          "BACKEND": "django.core.cache.backends.redis.RedisCache",
          "LOCATION": os.getenv("REDIS_URL", "redis://127.0.0.1:6379/1"),
      }
  }

  MAILERS = {
      "default": {
          "BACKEND": os.getenv(
              "EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend"
          ),
          "OPTIONS": {
              "host": os.getenv("EMAIL_HOST", "localhost"),
              "port": int(os.getenv("EMAIL_PORT", 587)),
              "username": os.getenv("EMAIL_HOST_USER", ""),
              "password": os.getenv("EMAIL_HOST_PASSWORD", ""),
              "use_tls": os.getenv("EMAIL_USE_TLS", "True").lower() == "true",
          },
      }
  }
  DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "noreply@example.com")

  SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "True").lower() == "true"
  SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", 31536000))
  SECURE_HSTS_INCLUDE_SUBDOMAINS = True
  SECURE_HSTS_PRELOAD = True
  SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
  ```
- **Verification Command:** `SECRET_KEY=deploykey32byteslongforcheck12345 pdm run deploy-check`.

---

### `BUG-01`: Fix Typo `MSG_PASWORD_RESET` Across All Consumers

- **Target Files:**
  - `core/shared/response_messages.py`
  - `core/shared/docs.py`
  - `core/password_reset/views.py`
  - `tests/test_password_reset.py`
- **Implementation:**
  1. Define `MSG_PASSWORD_RESET = _("Password has been reset successfully.")` in `core/shared/response_messages.py`.
  2. Keep `MSG_PASWORD_RESET = MSG_PASSWORD_RESET` alias temporarily for backward compatibility.
  3. Replace import and usage in `core/password_reset/views.py`, `core/shared/docs.py`, and `tests/test_password_reset.py`.
- **Verification Command:** `pdm run schema-check && pdm run lint && pdm run test tests.test_password_reset`.

---

### `NET-01`: Trusted Reverse Proxy Client IP Extraction

- **Target Files:**
  - `app/settings/base.py`
  - `core/shared/utils.py` (new) or `core/auth/rate_limit.py`
  - Auth & registration views
- **Implementation:**
  1. In `app/settings/base.py`, add `NUM_PROXIES = int(os.getenv("NUM_PROXIES", 0))`.
  2. Implement extractor:
     ```python
     def get_client_ip(request) -> str:
         remote_addr = request.META.get("REMOTE_ADDR", "127.0.0.1")
         num_proxies = getattr(settings, "NUM_PROXIES", 0)
         if num_proxies <= 0:
             return remote_addr
         xff = request.META.get("HTTP_X_FORWARDED_FOR")
         if not xff:
             return remote_addr
         ips = [ip.strip() for ip in xff.split(",") if ip.strip()]
         return ips[-num_proxies] if len(ips) >= num_proxies else ips[0]
     ```
  3. Update views to pass `get_client_ip(request)` into rate limiters and session creators.
- **Verification Command:** `pdm run test tests.test_rate_limit`.

---

### `DEV-01`: Safe Local Fallback for `SECRET_KEY` in Dev Settings

- **Target Files:**
  - `app/settings/dev.py`
- **Implementation:**
  ```python
  SECRET_KEY = os.getenv(
      "SECRET_KEY",
      "django-insecure-dev-fallback-secret-key-with-at-least-thirty-two-bytes-12345",
  )
  ```
- **Verification Command:** `pdm run check`.

---

### `CLEAN-01` to `CLEAN-04` & `I18N-01`: Code Hygiene & Message Centralization

1. `CLEAN-01`: Delete unused `IsUserOwner` in `core/shared/permissions/is_user.py`.
2. `CLEAN-02`: Remove redundant `try ... except Exception as e: raise e` in `core/shared/email_token_sender.py`.
3. `CLEAN-03`: Move mid-file `from django.conf import settings` to top in `core/models/user.py`.
4. `CLEAN-04`: Replace empty docstring `""" """` in `core/models/email_change.py` with descriptive docstring.
5. `I18N-01`: Centralize strings in `core/shared/response_messages.py` (`MSG_EMAIL_IN_USE`, `MSG_INVALID_PASSWORD`) and replace hardcoded literals in `core/email_change/services.py`.
- **Verification Command:** `pdm run lint && pdm run test tests.test_email_change`.

---

## 4. Sequential Execution Batches

```
Batch 1 (Immediate Hygiene & Crypto Fix):
SEC-01 -> DEV-01 -> BUG-01 -> CLEAN-01 -> CLEAN-02 -> CLEAN-03 -> CLEAN-04 -> I18N-01
Commands: pdm run lint && pdm run test

Batch 2 (Privacy & Cookie Scope):
SEC-02 -> SEC-03 -> SEC-05
Commands: pdm run schema-check && pdm run test tests.test_users tests.test_auth tests.test_contracts

Batch 3 (Concurrency, Proxy & Rate Limiting):
SEC-04 -> SEC-06 -> NET-01 -> ARCH-01
Commands: pdm run test tests.test_rate_limit tests.test_registration tests.test_password_reset tests.test_email_change

Batch 4 (Production Configuration & Deploy Check):
PROD-01
Commands: pdm run verify && pdm run deploy-check
```
