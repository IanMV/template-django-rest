from pathlib import Path
from tomllib import loads

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parent.parent


class ContainerConfigurationTests(SimpleTestCase):
    def test_compose_scripts_select_explicit_profiles(self):
        scripts = loads((ROOT / "pyproject.toml").read_text())["tool"]["pdm"]["scripts"]
        self.assertEqual(
            scripts["compose:dev"], "docker compose -f docker-compose.dev.yml"
        )
        self.assertEqual(
            scripts["compose:prod"], "docker compose -f docker-compose.yml"
        )

    def test_image_uses_non_root_gunicorn_without_startup_migrations(self):
        dockerfile = (ROOT / "Dockerfile").read_text()
        self.assertIn('CMD ["gunicorn"', dockerfile)
        self.assertIn("USER django", dockerfile)
        self.assertNotIn("runserver", dockerfile)
        self.assertNotIn("manage.py migrate", dockerfile)
