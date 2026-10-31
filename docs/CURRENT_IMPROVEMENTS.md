# Open Improvements

Constraint: Preserve `AGENTS.md` security boundaries, public URLs, CSRF, cookie flags, one-time-code semantics, and existing tests. Completed backlog specifications remain in git history.

- `AUTH-REAUTH`: Email change request, self-deactivation, and other-session deletion require a valid DB-backed session but not a fresh password or code; agree on a step-up authentication contract before changing public APIs. No direct password-change endpoint exists.
- `AUDIT-01`: `pdm run pip-audit` reported 31 vulnerability records in installed `filelock` 3.32.2 and `virtualenv` 21.7.4; dependency changes were outside the authorized scope. Review advisories and upgrade independently.
