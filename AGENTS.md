# Agent rules

## Work

- Inspect `git status` before edits. Preserve unrelated work. Never reset, checkout, rebase, amend, push, or bypass hooks.
- Make small logical commits: `fix:`, `refactor:`, `doc:`. Commit docs last.
- Do not read, print, or expose environment values or `.env`.
- Do not run tests or `pdm run verify` unless the user asks. Run only requested tests. Static checks allowed.
- Do not run Docker/Compose without explicit authorization; parse configuration statically instead.
- End each response: changes, rationale/trade-offs, pending work/risk.

## Structure

- Keep models in `core/models/`; never move them.
- Routes: `app/urls.py`; shared docs/routes: `core/shared/`; feature logic: feature `services.py`; session views: `core/auth/session_views.py`.
- Cross-feature imports: `core.models`, `core.shared`, public `core.auth/{services,authenticate,cookies,rate_limit}`, `core.audit.services` only.
- Manual test UI: `core/shared/manual.py`, `core/templates/manual/`, `core/static/manual/`; gate on `DEBUG`, use same-origin requests, never bypass API auth or store tokens.
- Settings: `dev` for SQLite/eager/console; `integrated` imports production services and disables production HTTP/cookie flags; `prod` requires injected configuration and never loads dotenv. Keep TLS proxy trust opt-in outside Compose.
- Containers: `Dockerfile.dev` for local stacks; `Dockerfile` for nonroot Gunicorn. Keep migrations/static collection in one release process, Beat single-instance, service secrets scoped, and data-service ports private.
- Preserve route order/names, API schemas/statuses, CSRF, cookie names/paths, and response contracts.

## Security conventions

- Cookie-only JWT auth. Unsafe requests require `X-CSRFTOKEN`.
- Mutations lock/recheck users; session changes use `SessionService`; cache invalidation runs on commit.
- Normalize complete emails to lowercase. Migration `0005` aborts on collisions; never merge automatically.
- Keep OTPs hashed, six digits, 15 minutes, five attempts. Queue email on commit; never log credentials, tokens, OTPs, or raw issuance exceptions.
- Production: PostgreSQL, Redis, secure cookies; Redis DBs: cache base, sessions `+1`, broker `+2`.

## Commands

- Install: `pdm install -G dev`
- Dev: `pdm run migrate`; `pdm run dev`
- Containers: `pdm run dev:up`, `full:up`, `prod:up`; matching `:down`/`:logs`. Generic wrappers: `compose:dev`, `compose:full`, `compose:prod` (each selects its own env file). See README for human setup; never inspect real env files.
- Static: `pdm run lint`; `pdm run schema-check`; `pdm run migrations-check`
- Targeted test: `pdm run test <label>`
- Integration test: `pdm run test <label> --settings=tests.settings_integration --noinput`
- Full verification, only when requested: `pdm run verify`

## Test conventions

- Use `ApiCase`/`ApiTransactionCase`; run on-commit callbacks explicitly in `TestCase`.
- Read raw OTPs only from `mail.outbox`. No sleeps or timing-based concurrency tests.
- Integration Redis keys use run-specific `template-auth-test:` prefixes. Never flush shared Redis; clear only test prefixes/limiter keys.
