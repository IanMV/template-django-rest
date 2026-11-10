from pathlib import Path
from tomllib import loads

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parent.parent


class ContainerConfigurationTests(SimpleTestCase):
    def test_compose_scripts_select_explicit_profiles(self):
        scripts = loads((ROOT / "pyproject.toml").read_text())["tool"]["pdm"]["scripts"]
        self.assertEqual(
            scripts["compose:dev"],
            "docker compose --env-file .env -f docker-compose.dev.yml",
        )
        self.assertEqual(
            scripts["compose:prod"],
            "docker compose --env-file .env -f docker-compose.yml",
        )

    def test_local_commands_load_environment_but_select_development_explicitly(self):
        scripts = loads((ROOT / "pyproject.toml").read_text())["tool"]["pdm"]["scripts"]
        for name, command in (
            ("dev", "runserver"),
            ("migrate", "migrate"),
            ("check", "check"),
            ("cleanup", "cleanup_auth"),
        ):
            with self.subTest(script=name):
                self.assertEqual(
                    scripts[name],
                    {
                        "cmd": f"python manage.py {command} --settings=app.settings.dev",
                        "env_file": ".env",
                    },
                )
        self.assertEqual(
            scripts["deploy-check"],
            {
                "cmd": "python manage.py check --deploy --settings=app.settings.prod",
                "env_file": ".env",
            },
        )

    def test_validation_scripts_do_not_load_environment_files(self):
        scripts = loads((ROOT / "pyproject.toml").read_text())["tool"]["pdm"]["scripts"]
        self.assertNotIn("_", scripts)
        for name in ("test", "migrations-check", "schema-check"):
            with self.subTest(script=name):
                self.assertIsInstance(scripts[name], str)
                self.assertIn("--settings=tests.settings", scripts[name].split())
        self.assertEqual(
            scripts["test:postgres"],
            "python manage.py test --settings=tests.settings_integration --noinput",
        )
        self.assertEqual(scripts["lint"], "ruff check")
        self.assertEqual(scripts["format"], "ruff format")

    def test_image_uses_non_root_gunicorn_without_startup_migrations(self):
        dockerfile = (ROOT / "Dockerfile").read_text()
        self.assertIn('CMD ["gunicorn"', dockerfile)
        self.assertIn("USER django", dockerfile)
        self.assertNotIn("runserver", dockerfile)
        self.assertNotIn("manage.py migrate", dockerfile)
