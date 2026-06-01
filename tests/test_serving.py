from __future__ import annotations

import io
import json
import wave

import pytest
from auralynq.pipeline import build_index
from auralynq.serving.app import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def client(corpus_dir):
    build_index(corpus_dir)
    from auralynq.agent import runner

    runner._CACHE.clear()
    app = create_app()
    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert any(p["subsystem"] == "llm" for p in body["providers"])
    assert "X-Request-ID" in r.headers


def test_metrics(client):
    client.get("/health")
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "requests_total" in r.json()


def test_query_grounded(client):
    r = client.post("/query", json={"question": "What is the capital of France?"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"]
    assert body["citations"]
    assert body["request_id"]
    assert {"name"}  # trace present
    assert any(sp["name"] == "citation_validator" for sp in body["trace"])


def test_query_stream_sse(client):
    with client.stream("POST", "/query/stream", json={"question": "What is PathRAG?"}) as r:
        assert r.status_code == 200
        events = [line for line in r.iter_lines() if line]
    assert any("final" in e for e in events)


def test_ingest_upload(client):
    content = b"# Upload\n\nQdrant stores dense and sparse vectors for hybrid search."
    r = client.post("/ingest", files={"file": ("note.md", content, "text/markdown")})
    assert r.status_code == 200
    assert r.json()["documents"] >= 1


def test_voice_endpoint(client, tmp_path):
    audio = io.BytesIO()
    with wave.open(audio, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 16000)
    # No sidecar => empty transcript, but endpoint must respond gracefully.
    r = client.post("/voice", files={"file": ("q.wav", audio.getvalue(), "audio/wav")})
    assert r.status_code == 200
    assert "answer" in r.json()


def test_eval_report_pending(client):
    r = client.get("/eval/report")
    assert r.status_code == 200


def test_ws_voice_roundtrip(client):
    with client.websocket_connect("/ws/voice") as ws:
        ws.send_bytes(b"\x00\x00" * 100)
        ack = ws.receive_json()
        assert ack["type"] == "ack"
        ws.send_text(json.dumps({"action": "end"}))
        msg = ws.receive_json()
        assert msg["type"] == "transcript"
        final = ws.receive_json()
        assert final["type"] == "final"
        ws.close()


def test_version_endpoint(client):
    r = client.get("/version")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "auralynq"
    assert body["version"]
    assert body["api"] == "v1"


def test_ready_endpoint_reports_index(client):
    # the `client` fixture indexes a corpus, so the service is ready
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["ready"] is True
    assert r.json()["vectors"] >= 1
