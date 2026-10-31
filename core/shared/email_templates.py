from django.template.loader import render_to_string

SUBJECTS = {
    "verification_code": "Verify your e-mail",
    "password_reset": "Your password reset code",
    "email_change": "Confirm your new e-mail address",
}


def render_email_token(template_name: str, code: str) -> tuple[str, str, str]:
    subject = SUBJECTS[template_name]
    context = {"code": code}
    text = render_to_string(f"email/{template_name}.txt", context).strip()
    html = render_to_string(f"email/{template_name}.html", context).strip()
    return subject, text, html
