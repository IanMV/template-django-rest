from pathlib import Path
from tomllib import loads

import yaml
from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parent.parent


class ContainerConfigurationTests(SimpleTestCase):
    def test_development_modes_are_isolated(self):
        simple = yaml.safe_load((ROOT / "docker-compose.dev.yml").read_text())
        full = yaml.safe_load((ROOT / "docker-compose.integrated.yml").read_text())
        self.assertEqual(set(simple["services"]), {"app"})
        self.assertEqual(
            simple["services"]["app"]["environment"]["DJANGO_SETTINGS_MODULE"],
            "app.settings.dev",
        )
        self.assertEqual(
            full["services"]["app"]["environment"]["DJANGO_SETTINGS_MODULE"],
            "app.settings.integrated",
        )
        self.assertEqual(
            set(full["services"]), {"app", "migrate", "db", "redis", "worker", "beat"}
        )
        self.assertNotEqual(simple["name"], full["name"])
        for configured in (simple, full):
            self.assertTrue(
                configured["services"]["app"]["ports"][0].startswith("127.0.0.1:")
            )

    def test_production_gates_startup_and_keeps_internal_services_private(self):
        production = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
        services = production["services"]
        self.assertEqual(
            services["app"]["environment"]["DJANGO_SETTINGS_MODULE"],
            "app.settings.prod",
        )
        self.assertEqual(services["app"]["environment"]["TRUST_PROXY_HEADERS"], "true")
        for name in ("app", "worker", "beat"):
            self.assertEqual(
                services[name]["depends_on"]["release"]["condition"],
                "service_completed_successfully",
            )
            self.assertTrue(services[name]["read_only"])
        for name in ("app", "db", "redis"):
            self.assertNotIn("ports", services[name])
        for name in ("app", "db", "redis", "worker", "beat", "proxy"):
            self.assertIn("healthcheck", services[name])
        dockerfile = (ROOT / "Dockerfile").read_text()
        self.assertIn('CMD ["gunicorn"', dockerfile)
        self.assertNotIn("runserver", dockerfile)
        self.assertEqual(services["release"]["restart"], "no")

    def test_compose_scripts_use_explicit_environment_files(self):
        scripts = loads((ROOT / "pyproject.toml").read_text())["tool"]["pdm"]["scripts"]
        for mode, filename in (
            ("dev", ".env.dev"),
            ("full", ".env.integrated"),
            ("prod", ".env.prod"),
        ):
            self.assertIn(f"--env-file {filename}", scripts[f"compose:{mode}"])
        self.assertIn(".env*", (ROOT / ".dockerignore").read_text().splitlines())
