"""Every page of the React website must be served, so reloading or bookmarking it works."""
import re
from pathlib import Path

from test_admin_camera_api import AdminApiTestCase

INDEX_JS = Path(__file__).resolve().parents[2] / "frontend" / "smart-sec-cam" / "src" / "index.js"


class FrontendRoutesTest(AdminApiTestCase):
    def test_every_website_page_has_a_server_route(self):
        pages = {path.strip("/") for path in re.findall(r'<Route\s+path="([^"]*)"', INDEX_JS.read_text())}
        self.assertIn("dashboard", pages)
        served = {rule.rule.strip("/") for rule in self.server.app.url_map.iter_rules()
                  if rule.endpoint.startswith("serve_react_ui")}
        self.assertEqual(sorted(pages - served), [], "website pages with no server route")
