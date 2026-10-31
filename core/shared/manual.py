from django.conf import settings
from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

EMAIL = ("email", "E-mail", "email")
PASSWORD = ("password", "Senha atual", "password")
CODE = ("code", "Código recebido por e-mail", "text")
NEW_EMAIL = ("new_email", "Novo e-mail", "email")
PAGINATION = [
    ("page", "Página (opcional)", "number"),
    ("page_size", "Itens por página (opcional, até 100)", "number"),
]

# Each entry describes an existing endpoint, not a separate implementation of its rules.
PAGES = {
    "auth": (
        "Acesso e sessões",
        [
            ("login", "GET", "Obter proteção CSRF", [], ""),
            (
                "login",
                "POST",
                "Entrar",
                [EMAIL, PASSWORD, ("remember_me", "Lembrar de mim", "checkbox")],
                "",
            ),
            ("refresh", "POST", "Renovar acesso", [], ""),
            ("logout", "POST", "Sair deste dispositivo", [], ""),
            ("user-sessions-list", "GET", "Listar minhas sessões", [], ""),
            (
                "user-sessions-deactivate",
                "DELETE",
                "Encerrar outra sessão",
                [("session_id", "ID da sessão obtido na listagem", "number")],
                "Encerrar essa sessão? A sessão atual não pode ser encerrada por esta operação.",
            ),
            (
                "revoke-sessions",
                "POST",
                "Encerrar todas as sessões",
                [],
                "Encerrar todas as suas sessões, incluindo esta?",
            ),
        ],
    ),
    "codes": (
        "Cadastro e recuperação",
        [
            ("registration-request", "POST", "Cadastro — 1. Pedir código", [EMAIL], ""),
            (
                "registration-verify",
                "POST",
                "Cadastro — 2. Conferir código",
                [EMAIL, CODE],
                "",
            ),
            (
                "registration-confirm",
                "POST",
                "Cadastro — 3. Confirmar conta",
                [
                    EMAIL,
                    CODE,
                    ("name", "Nome", "text"),
                    ("password", "Nova senha", "password"),
                ],
                "",
            ),
            (
                "password-reset-request",
                "POST",
                "Recuperação — 1. Pedir código",
                [EMAIL],
                "",
            ),
            (
                "password-reset-verify",
                "POST",
                "Recuperação — 2. Conferir código",
                [EMAIL, CODE],
                "",
            ),
            (
                "password-reset-confirm",
                "POST",
                "Recuperação — 3. Alterar senha",
                [EMAIL, CODE, ("new_password", "Nova senha", "password")],
                "Alterar a senha e encerrar todas as sessões dessa conta?",
            ),
            (
                "email-change-request",
                "POST",
                "Troca de e-mail — 1. Pedir código",
                [NEW_EMAIL, PASSWORD],
                "",
            ),
            (
                "email-change-verify",
                "POST",
                "Troca de e-mail — 2. Conferir código",
                [CODE],
                "",
            ),
            (
                "email-change-confirm",
                "POST",
                "Troca de e-mail — 3. Confirmar troca",
                [CODE, PASSWORD],
                "Trocar o e-mail e encerrar todas as suas sessões?",
            ),
        ],
    ),
    "account": (
        "Conta, equipe e documentação",
        [
            ("me", "GET", "Consultar meu perfil", [], ""),
            (
                "deactivate-self",
                "POST",
                "Desativar minha conta",
                [PASSWORD],
                "Desativar sua conta e encerrar todas as sessões? Você não poderá reativá-la pelo cadastro.",
            ),
            ("users-list", "GET", "Listar usuários ativos (equipe)", PAGINATION, ""),
            ("audit-list", "GET", "Consultar auditoria (equipe)", PAGINATION, ""),
            ("schema", "GET", "Consultar esquema da API", [], ""),
        ],
    ),
}


@never_cache
@require_safe
def manual_page(request, page="auth"):
    if not settings.DEBUG or page not in PAGES:
        raise Http404
    title, entries = PAGES[page]
    forms = []
    for name, method, label, fields, confirmation in entries:
        action = reverse(
            name,
            kwargs={"session_id": 0} if name == "user-sessions-deactivate" else None,
        )
        if name == "schema":
            action += "?format=json"
        forms.append(
            {
                "name": name,
                "method": method,
                "label": label,
                "fields": fields,
                "action": action,
                "confirmation": confirmation,
            }
        )
    return render(
        request,
        "manual/page.html",
        {
            "title": title,
            "forms": forms,
            "pages": [(key, value[0]) for key, value in PAGES.items()],
            "csrf_cookie_name": settings.CSRF_COOKIE_NAME,
            "csrf_header_name": settings.CSRF_HEADER_NAME.removeprefix("HTTP_").replace(
                "_", "-"
            ),
        },
    )
