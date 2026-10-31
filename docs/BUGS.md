# Current Improvements Backlog

> **Constraint:** Preserve [AGENTS.md](../AGENTS.md) security boundaries, URLs, response contracts, CSRF, cookies, sessions, and one-time-code semantics. Run tests only when explicitly requested.

## Review of `docs: bugs`

All identified correctness bugs and requested coverage are addressed in code. The reported 114-test run preceded this review's final changes; tests were not rerun here.

| Item | Result | Evidence / disposition |
| --- | --- | --- |
| 1.1 malformed session claim | Fixed | Reject non-positive/non-integer claims before ORM filter; test string, float, bool, zero, negative. |
| 1.2 active registration verify | Fixed | Query inactive accounts only; test lingering code against active account. |
| 1.3 test isolation | Fixed | Reset default/session caches and mail outbox in `BehaviorHelpers`; remove session-cache-specific setup. |
| 1.4 issuance logging | Fixed | Log registration and email-change issuance exceptions without logging secrets. |
| 2.1 refresh JWT reparse | Fixed | Read rotated access/refresh JTIs from validated token objects. |
| 2.2 authenticated token reuse | Fixed | Pass `request.auth` to session services; use claim for current-session checks, DB fallback for legacy token. |
| 2.3 revoke/login query growth | Fixed | Bulk blacklist and session update for revoke-all and login replacement; invalidate collected IDs on commit. Query count is bounded; bulk lists still use memory proportional to affected sessions. |
| 2.4 legacy cookie header overwrite | False positive for current callers | Login/refresh and revocation responses have no preexisting raw `Set-Cookie` header; Django emits `response.cookies` separately from the legacy-path header. Contract tests assert new-path cookie plus legacy-path deletion. If another caller starts setting raw `Set-Cookie` before this helper, revisit. `response.headers.appendlist()` does not exist. |
| 3.1 dead auth comments/flag | Fixed | Removed commented bearer-auth branch and redundant cookie flag; cookie-only CSRF enforcement remains. |
| 3.2 misspelled alias | Fixed | No in-repo callers; removed `MSG_PASWORD_RESET`. External Python imports of the typo are not supported. |
| 3.3 empty permissions package | Fixed | Removed unused package initializer. |
| 3.4 canonical model exports | Fixed | `core.models` exports canonical concrete and abstract models; model app label remains `core`. |
| 4.1 cookie assertions | Fixed | Assert login access/refresh paths and configured max-age. |
| 4.2 malformed session test | Fixed | Verify malformed claim values return 401. |
| 4.3 active-account verify test | Fixed | Verify active-account lingering code returns 400. |
| 4.4 throttle test cost | Fixed | Seed 29 attempts, issue request 30 (401) and 31 (429); retain threshold coverage with two requests rather than 31. |
