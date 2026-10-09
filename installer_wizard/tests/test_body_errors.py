import unittest

from body_errors import install
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient


class MalformedBodyTest(unittest.TestCase):
    def test_bad_json_and_bad_encoding_are_client_errors(self):
        app = FastAPI()
        install(app)

        @app.post("/echo")
        async def echo(request: Request):
            return await request.json()

        client = TestClient(app)
        self.assertEqual(client.post("/echo", content=b'{"text":"ciao"}').json(), {"text": "ciao"})
        self.assertEqual(client.post("/echo", content=b"{broken").status_code, 400)
        self.assertEqual(client.post("/echo", content='{"text":"è"}'.encode("cp1252")).status_code, 400)


if __name__ == "__main__":
    unittest.main()
