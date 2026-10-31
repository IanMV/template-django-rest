# Django REST authentication template

Cookie-based Django REST authentication API. It manages account registration, login, device sessions, password recovery, email changes, security audit records, and scheduled cleanup.

## Business rules

- An email address identifies one account. The whole address is case-insensitive and stored lowercase.
- Registration is a three-step email-code flow. Only an unfinished account may complete registration; an established disabled account cannot reactivate through registration.
- A registration, reset, or email-change code has six digits, is stored hashed, expires after 15 minutes, and is unusable after five incorrect attempts.
- Code verification does not consume a code. Confirmation consumes it and changes state atomically.
- Existing active accounts receive a registration security notice instead of a registration code. Request responses stay uniform.
- Password reset requests have a uniform response for unknown or inactive accounts. Successful resets revoke all sessions and clear browser authentication cookies.
- Email change requires the current password when requesting and confirming. Confirmation requires a unique new email, revokes all sessions, clears browser cookies, and invalidates pending password-reset codes.
- Password values are exact. Leading or trailing spaces are part of the password; whitespace-only values are rejected.
- Users can deactivate themselves only with their current password. Staff users can list active users; audit records are staff-only.

## Functional requirements

### Authentication and sessions

- `GET /api/login/` issues the CSRF cookie. `POST /api/login/` requires CSRF and sets HttpOnly access and refresh cookies; it returns only a detail response.
- Access and refresh tokens are tied to an active server-side session. Login replaces a session from the same user, device, and IP.
- Access tokens last 15 minutes. Refresh inactivity is one day, or seven days with `remember_me`; both have a 30-day absolute limit.
- `POST /api/refresh/` requires CSRF, rotates both tokens, and detects refresh reuse. Reuse revokes the session.
- Logout, session deletion, self-deactivation, password reset, and confirmed email change revoke sessions. A session cannot delete itself through the device-session endpoint.
- The session list reports active sessions and marks the current session.

### Abuse controls and audit

- Login allows 30 attempts per IP and 10 per IP/email in five minutes. A successful login clears the IP/email counter.
- Code issuance has a two-second IP burst limit and a 60-second per-email cooldown. Verification allows 15 attempts per IP per minute.
- Current-password checks allow five failures per user in five minutes across email change and self-deactivation.
- Security events record allowlisted metadata only. Unknown-login emails are hashed; credentials, tokens, CSRF values, and OTPs are not recorded.

### Background work and retention

- Transactional email is queued after database commit. Queue failures remove undelivered registration/email-change codes; password reset keeps its uniform response and removes its code.
- Email sends text and HTML bodies. SMTP/network failures retry up to three times; SMTP socket operations time out after 10 seconds.
- One Celery Beat process schedules daily maintenance at 03:00 `America/Sao_Paulo`: abandoned unfinished registrations, stale/expired sessions, expired JWT token records, and optionally expired audit entries are removed.
- Audit retention is disabled unless `AUDIT_RETENTION_DAYS` is a positive value.

## Non-functional requirements

- Production settings require PostgreSQL, Redis, a nonempty secret key, allowed hosts, and CSRF trusted origins. PostgreSQL provides row-level locks for security mutations.
- Cookies are secure in production. HTTPS redirect and one-year HSTS are enabled by default.
- Redis is shared by web and worker processes. Cache, session cache, and Celery broker use separate database indexes.
- Security-sensitive state changes use database transactions and row locks. Cache invalidation failure can leave a positive session-cache entry valid for at most 60 seconds.
- Migration `0005_normalize_user_email` stops before changing data if canonical email collisions exist. Resolve collisions manually; accounts are never merged automatically.
- Production audit writes are best effort. The API does not make audit storage tamper-proof.

## Docker environment

1. Copy `.env.example` to `.env` and replace every required placeholder.
2. Run `docker compose up --build`.
3. The `app` service runs migrations before serving on `http://localhost:8000`.

Compose starts `app`, PostgreSQL, and Redis. PostgreSQL and Redis have persistent named volumes and health checks; the app waits for both to report healthy. Redis is private to the Compose network and uses `redis://` accordingly.

**To confirm:** this repository has no production WSGI/ASGI server dependency. The Compose app uses Django `runserver --noreload` for an integrated development environment, not a production HTTP deployment. Choose and configure the production server and reverse proxy before deployment.

## To confirm

- Legal audit-retention duration and PostgreSQL append-only permissions.
- Trusted proxy topology before enabling `NUM_PROXIES` or relying on `X-Forwarded-Proto`.
- SMTP provider, sender identity, and real delivery monitoring.
- Production static-file serving strategy.
