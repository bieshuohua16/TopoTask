"""Topology drawing shares global configuration without exposing credentials."""
from __future__ import annotations

import io
import json
import sqlite3
import urllib.error
from unittest import mock

from db import get_db
from services_ai import save_ai_config
from tests.support import ApiTestCase


class TopologyAITest(ApiTestCase):
    messages = [{"role": "system", "content": "Return JSON"}, {"role": "user", "content": "Draw a router"}]

    def configure(self, **changes):
        return save_ai_config({
            "api_base": "https://model.example/v1", "model": "drawing-model",
            "api_key": "private-key-for-topology", "temperature": 0.4, **changes,
        })

    def test_uses_latest_global_settings_and_streams_without_exposing_key(self):
        self.configure()
        for model, base in (("drawing-model", "https://model.example/v1"),
                            ("changed-model", "https://changed.example/v1")):
            with self.subTest(model=model):
                self.api("PUT", "/api/ai/config", {"model": model, "api_base": base})
                event = b'data: {"choices":[{"delta":{"content":"{\\"action\\":\\"add\\"}"}}]}\n\n'
                upstream = io.BytesIO(event + b"data: [DONE]\n\n")
                with mock.patch("services_ai.urllib.request.urlopen", return_value=upstream) as call:
                    response = self.client.post("/api/ai/topology", json={
                        "messages": self.messages, "model": "browser-override",
                        "api_base": "https://ignored.example", "api_key": "ignored",
                    })
                    data = response.get_data()
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.mimetype, "text/event-stream")
                self.assertEqual(data, event + b"data: [DONE]\n\n")
                self.assertNotIn(b"private-key-for-topology", data)
                request = call.call_args.args[0]
                self.assertEqual(request.full_url, base + "/chat/completions")
                self.assertEqual(request.get_header("Authorization"), "Bearer private-key-for-topology")
                body = json.loads(request.data)
                self.assertEqual(body["model"], model)
                self.assertEqual(body["temperature"], 0.4)
                self.assertEqual(body["messages"], self.messages)
                self.assertTrue(body["stream"])
                self.assertEqual(body["response_format"], {"type": "json_object"})
                self.assertNotIn("thinking", body)
                self.assertTrue(upstream.closed)

    def test_local_model_needs_no_api_key(self):
        self.configure(api_base="http://127.0.0.1:11434/v1", api_key="")
        with mock.patch("services_ai.urllib.request.urlopen", return_value=io.BytesIO(b"data: [DONE]\n\n")) as call:
            response = self.client.post("/api/ai/topology", json={"messages": self.messages})
            response.get_data()
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(call.call_args.args[0].get_header("Authorization"))

    def test_invalid_messages_and_missing_configuration_do_not_contact_model(self):
        invalid = [None, {}, [], ["bad"], [{"role": "tool", "content": "bad"}],
                   [{"role": [], "content": "bad"}],
                   [{"role": "user", "content": {}}], self.messages * 22]
        with mock.patch("services_ai.urllib.request.urlopen") as call:
            for messages in invalid:
                response = self.client.post("/api/ai/topology", json={"messages": messages})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.get_json()["error"]["code"], "invalid_messages")
            response = self.client.post("/api/ai/topology", json={"messages": self.messages})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.get_json()["error"]["code"], "ai_not_configured")
            call.assert_not_called()

    def test_legacy_global_configuration_is_available_to_drawing(self):
        self.new_project()
        get_db().execute("UPDATE projects SET todo_config=?", (json.dumps({
            "aiConfig": {"apiBase": "http://localhost:11434/v1", "model": "legacy-model"},
        }),))
        get_db().commit()
        with mock.patch("services_ai.urllib.request.urlopen", return_value=io.BytesIO(b"data: [DONE]\n\n")) as call:
            response = self.client.post("/api/ai/topology", json={"messages": self.messages})
            response.get_data()
        self.assertEqual(json.loads(call.call_args.args[0].data)["model"], "legacy-model")
        self.assertEqual(self.get_json("/api/ai/config")["model"], "legacy-model")

    def test_provider_failure_returns_api_error_before_stream_starts(self):
        self.configure()
        for exception, status, code in (
            (urllib.error.HTTPError("https://model.example", 401, "Unauthorized", {}, io.BytesIO(b"{}")),
             502, "ai_upstream_error"),
            (TimeoutError("slow"), 504, "ai_timeout"),
        ):
            with self.subTest(code=code):
                with mock.patch("services_ai.urllib.request.urlopen", side_effect=exception):
                    response = self.client.post("/api/ai/topology", json={"messages": self.messages})
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.get_json()["error"]["code"], code)

    def test_stream_failure_is_reported_and_response_closed(self):
        self.configure()
        upstream = mock.Mock()
        upstream.__iter__ = mock.Mock(return_value=iter([b'data: {"choices":[]}\n\n']))

        def broken():
            yield b'data: {"choices":[]}\n\n'
            raise OSError("disconnected")

        upstream.__iter__.return_value = broken()
        with mock.patch("services_ai.urllib.request.urlopen", return_value=upstream):
            response = self.client.post("/api/ai/topology", json={"messages": self.messages})
            data = response.get_data(as_text=True)
        self.assertIn('"error"', data)
        upstream.close.assert_called_once()

    def test_waiting_for_model_does_not_block_database_writes(self):
        self.configure()
        project = self.new_project()

        def open_response(*_args, **_kwargs):
            with sqlite3.connect(self.db_path, timeout=0.05) as other:
                other.execute("UPDATE projects SET owner='Available' WHERE id=?", (project["id"],))
            return io.BytesIO(b"data: [DONE]\n\n")

        with mock.patch("services_ai.urllib.request.urlopen", side_effect=open_response):
            response = self.client.post("/api/ai/topology", json={"messages": self.messages})
            response.get_data()
        self.assertEqual(self.get_json(f"/api/projects/{project['id']}")["owner"], "Available")

    def test_closing_browser_stream_closes_upstream(self):
        self.configure()
        upstream = io.BytesIO(b'data: {"choices":[]}\n\n' * 5)
        with mock.patch("services_ai.urllib.request.urlopen", return_value=upstream):
            response = self.client.post("/api/ai/topology", json={"messages": self.messages}, buffered=False)
            response.close()
        self.assertTrue(upstream.closed)
