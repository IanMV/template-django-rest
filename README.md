# Template de Projeto Base para Django REST Framework

**Objetivo:** template de autenticação com Django REST Framework.

## Desenvolvimento

Requer Python 3.14 e PDM. Na raiz do projeto:

```bash
pdm install -G dev
pdm run python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Salve a chave gerada em `.env` como `SECRET_KEY=<chave>` (`.env` é ignorado pelo Git). Depois:

```bash
pdm run migrate
pdm run dev
```

Para conferir o projeto inteiro (check do Django, migrações, schema, Ruff e testes):

```bash
pdm run verify
```

Também é possível rodar etapas isoladas: `pdm run check`, `pdm run migrations-check`, `pdm run schema-check`, `pdm run lint` e `pdm run test tests.test_auth`. `pdm run format` **altera arquivos**; não faz parte do `verify`. `schema-check` descarta o YAML em `/dev/null` (Unix). `pdm run deploy-check` usa settings de produção e exige `ALLOWED_HOSTS` e `SECRET_KEY` adequados.

## Production mail worker

- Set `DJANGO_SETTINGS_MODULE=app.settings.prod` explicitly for every worker; provide the required production settings and SMTP configuration through the deployment environment. Start a worker with `DJANGO_SETTINGS_MODULE=app.settings.prod pdm run celery -A app worker --loglevel=INFO`.
- Share the production Redis instance across web and worker processes; broker uses the cache DB index + 2. Use credentialed `rediss://` with verified TLS unless Redis is on a private network. Do not place OTPs or recipient addresses in logs.
- Queue failures invalidate issued codes (registration/email change: 503; password reset: uniform 200). Accepted mail may fail later; inspect worker error logs and let users request a new code.
- `remember_me` is optional on login. Standard/remembered refresh inactivity is 1/7 days; both absolute limits remain 30 days until the standard 7-day reduction receives approval.

## Audit and maintenance

- Apply migrations before enabling the audit endpoint; `GET /api/audit/` requires cookie authentication and staff privileges. Existing `/admin/` is unchanged; audit records are not registered there. Audit writes are best-effort and do not block login.
- Run exactly one Beat alongside the worker: `DJANGO_SETTINGS_MODULE=app.settings.prod pdm run celery -A app beat --loglevel=INFO`. Daily cleanup is scheduled at 03:00 `America/Sao_Paulo`; it deletes eligible registrations and expired/inactive sessions in batches and invokes Simple JWT's `flushexpiredtokens`.
- Configure a positive `AUDIT_RETENTION_DAYS` only after determining the applicable retention policy. Without it, audit records are not deleted by maintenance. Application-level read-only access does not guarantee database immutability; restrict PostgreSQL write/delete privileges before claiming tamper resistance.
- Audit and maintenance behavioral tests were not created or run under the current request; validate these flows with PostgreSQL/Redis in staging before production use.

## Estado atual

Rotas atuais: consulte `app/urls.py` e o mapa de fluxos em `AGENTS.md`.

## Lista de Tarefas

- [x] Logout assim que e-mail ou senha são alterados.
- [ ] Template visual para os códigos enviados por e-mail. Bem como adição de perfil de envio de códigos por e-mail, na configuração MAILERS.
- [ ] Adicionar *docstrings* nas classes e funções.
- [ ] Melhorar uso do drf-spectacular.
- [ ] Melhorar caminho das *urls* (usar *kebab-case* ou outro, invés de *snake_case*).
