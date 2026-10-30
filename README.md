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

## Estado atual

Rotas atuais: consulte `app/urls.py` e o mapa de fluxos em `AGENTS.md`.

## Lista de Tarefas

- [x] Logout assim que e-mail ou senha são alterados.
- [ ] Template visual para os códigos enviados por e-mail. Bem como adição de perfil de envio de códigos por e-mail, na configuração MAILERS.
- [ ] Adicionar *docstrings* nas classes e funções.
- [ ] Melhorar uso do drf-spectacular.
- [ ] Melhorar caminho das *urls* (usar *kebab-case* ou outro, invés de *snake_case*).
