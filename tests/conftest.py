import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FIXTURES = Path(__file__).parent / "fixtures"


class MockSite(BaseHTTPRequestHandler):
    """Behaves like armnab.am: unknown detail IDs return HTTP 200 with a not-found page."""
    fail_paths: set = set()
    seen_agents: list = []

    def do_GET(self):
        type(self).seen_agents.append(self.headers.get("User-Agent"))
        path = self.path.split("?")[0].rstrip("/")
        if path in self.fail_paths:
            self.send_response(500)
            self.end_headers()
            return
        if path == "/management-systems":
            target = FIXTURES / "list.html"
        elif path.startswith("/management-systems/MS"):
            candidate = FIXTURES / f"{path.rsplit('/', 1)[-1]}.html"
            target = candidate if candidate.exists() else FIXTURES / "not_found.html"
        else:
            self.send_response(404)
            self.end_headers()
            return
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def site():
    MockSite.fail_paths = set()
    MockSite.seen_agents = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockSite)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", MockSite
    server.shutdown()


# Stand-ins with an assumed shape. The real tables load from ../greece/prepare_certifind.py.
TABLES = {
    "NACE_TO_EA": {"01": "1", "05": "2", "10": "3", "41": "28", "85": "37", "26.11": "19"},
    "NACE_SPANS": [(58, 63, "33")],
    "FOOD_CATEGORIES": {letter: letter for letter in "ABCDEFGHIJK"},
    "ENERGY_AREAS": {letter: letter for letter in "ABCDEFGH"},
    "MEDICAL_AREAS": {f"A.1.{n}": n for n in range(1, 8)},
    "EXCLUDED_SCHEMES": ["AST ", "GOST"],
}


@pytest.fixture
def tables():
    return TABLES
