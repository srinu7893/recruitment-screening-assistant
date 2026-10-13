import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from screening.providers import DemoProvider
from screening.server import make_server
from screening.storage import Store
from screening.workflow import ScreeningService


class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = TemporaryDirectory()
        cls.token = "test-token-" + "x" * 32
        service = ScreeningService(Store(Path(cls.temp.name) / "api.sqlite3"), DemoProvider())
        cls.server = make_server(service, cls.token, port=0)
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temp.cleanup()

    def call(self, path, body=None, auth=True, **headers):
        if auth:
            headers["Authorization"] = f"Bearer {self.token}"
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = Request(self.base + path, headers=headers,
                          data=json.dumps(body).encode() if body is not None else None)
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, json.load(response)
        except HTTPError as response:
            return response.code, json.load(response)

    def test_authentication_required(self):
        self.assertEqual(self.call("/health", auth=False)[0], 401)

    def test_browser_origin_rejected(self):
        self.assertEqual(self.call("/health", Origin="https://example.invalid")[0], 403)

    def test_api_round_trip(self):
        folder = Path(__file__).resolve().parents[1] / "examples"
        role = json.loads((folder / "role.json").read_text())
        request = json.loads((folder / "profile-request.json").read_text())
        self.assertEqual(self.call("/roles", role)[0], 201)
        status, run = self.call("/screenings", request)
        self.assertEqual(status, 200)
        self.assertEqual(run["status"], "awaiting_review")
        self.assertEqual(self.call("/runs?id=" + request["request_id"])[1], run)
        self.assertEqual(self.call("/roles", role)[0], 409)
        self.assertEqual(self.call("/roles?version=backend-engineer%3Av1")[0], 200)

    def test_invalid_json_shape(self):
        self.assertEqual(self.call("/screenings", ["bad"])[0], 400)

    def test_unknown_resource(self):
        self.assertEqual(self.call("/runs?id=missing")[0], 404)


if __name__ == "__main__":
    unittest.main()
