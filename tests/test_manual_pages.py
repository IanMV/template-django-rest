from html.parser import HTMLParser
from urllib.parse import urlsplit

from django.test import SimpleTestCase, override_settings
from django.urls import URLPattern, URLResolver, get_resolver, reverse


class EndpointParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.endpoints = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.endpoints.add((attrs["data-method"], urlsplit(attrs["action"]).path))
        elif tag == "a":
            self.endpoints.add(("GET", urlsplit(attrs["href"]).path))


@override_settings(DEBUG=True)
class ManualPageTests(SimpleTestCase):
    def test_pages_cover_all_api_operations(self):
        parser = EndpointParser()
        for page in ("auth", "codes", "account"):
            response = self.client.get(reverse("manual-page", args=[page]))
            self.assertEqual(response.status_code, 200)
            self.assertIn("no-store", response["Cache-Control"])
            parser.feed(response.content.decode())

        def operations(patterns, prefix=""):
            for pattern in patterns:
                path = prefix + str(pattern.pattern)
                if isinstance(pattern, URLResolver):
                    yield from operations(pattern.url_patterns, path)
                elif isinstance(pattern, URLPattern) and path.startswith("api/"):
                    view = pattern.callback.view_class
                    kwargs = {"session_id": 0} if "session_id" in path else None
                    for method in ("get", "post", "delete", "put", "patch"):
                        if hasattr(view, method):
                            yield method.upper(), reverse(pattern.name, kwargs=kwargs)

        self.assertEqual(
            {entry for entry in parser.endpoints if entry[1].startswith("/api/")},
            set(operations(get_resolver().url_patterns)),
        )
        self.assertIn(("GET", reverse("admin:index")), parser.endpoints)

    @override_settings(DEBUG=False)
    def test_manual_pages_are_hidden_outside_debug(self):
        for path in ("/manual/", "/manual/auth/", "/manual/codes/", "/manual/account/"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_unknown_pages_and_unsafe_page_methods_are_rejected(self):
        self.assertEqual(self.client.get("/manual/unknown/").status_code, 404)
        self.assertEqual(self.client.post("/manual/").status_code, 405)

    @override_settings(
        CSRF_COOKIE_NAME="manualcsrf", CSRF_HEADER_NAME="HTTP_X_MANUAL_CSRF"
    )
    def test_configured_csrf_names_reach_javascript(self):
        response = self.client.get("/manual/")
        self.assertContains(response, 'data-csrf-cookie="manualcsrf"')
        self.assertContains(response, 'data-csrf-header="X-MANUAL-CSRF"')
