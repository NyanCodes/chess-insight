import json
import re
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from chess_backend.analysis import AnalysisConfig, Analyzer
from chess_backend.cli import default_engine
from chess_backend.explain import KEYS
from chess_backend.inputs import parse_pgn
from chess_backend.limits import job_slot
from web import app as web_app
from web.jobs import Job, JobRequest
from tests.fake_engine import FakeEngine
from tests.helpers import DATA, load_fixture

SCHOLAR = "[Event \"Scholar's Mate\"]\n\n1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7# 1-0\n"
FOOL = "[Event \"Fool's Mate\"]\n\n1. f3 e5 2. g4 Qh4# 0-1\n"


def make_client(tmp_path, *, engine=None, queue_timeout=0.3):
    engine = engine or FakeEngine()
    app = web_app.create_app(lock_dir=tmp_path, queue_timeout=queue_timeout,
                             analyzer_factory=lambda cfg: Analyzer(Path("fake"), cfg, engine=engine))
    return TestClient(app)


@pytest.fixture
def client(tmp_path):
    return make_client(tmp_path)


def wait_for(client, job_id, states=("done", "failed", "busy"), timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] in states:
            return job
        time.sleep(0.02)
    raise AssertionError(f"job stuck: {job}")


def analyse(client, pgn=SCHOLAR, **extra):
    response = client.post("/api/analyze", json={"pgn_text": pgn, **extra})
    assert response.status_code == 202, response.text
    return response.json()["job_id"]


# --- the happy path ------------------------------------------------------------

def test_analyse_poll_annotations_report(client):
    job_id = analyse(client)
    job = wait_for(client, job_id)
    assert job["state"] == "done" and job["progress"] == {"ply": 7, "total": 7}
    body = client.get(f"/api/annotations/{job_id}?locale=en").json()
    moves = body["games"][0]["moves"]
    assert [m["san"] for m in moves][-2:] == ["Nf6", "Qxf7#"] and body["locale"] == "en"
    blunder = moves[5]
    assert blunder["classification"] == "blunder" and blunder["side"] == "black" and blunder["number"] == 3
    assert {"key": "allowed_mate", "params": {"mate_in": 1, "reply": "Qxf7#"},
            "text": "It allowed mate in 1."} in blunder["annotations"]
    # The browser has no chess engine, so every row carries what the board needs.
    assert blunder["fen_before"].startswith("r1bqkb1r/pppp1ppp/2n5/4p2Q") or "Q" in blunder["fen_before"]
    assert blunder["fen_after"] != blunder["fen_before"]
    assert blunder["played_squares"] == {"from": "g8", "to": "f6"} and blunder["best_squares"]
    assert blunder["eval_after"]["mate_white"] == 1 and blunder["eval_after"]["mate_mover"] == -1
    report = client.get(f"/api/report/{job_id}?locale=en&player=both").json()
    assert "won by checkmate in 7 plies" in report["text"] and report["player"] == "both"


def test_progress_events_stream_until_the_job_ends(client):
    job_id = analyse(client)
    events = []
    with client.stream("GET", f"/api/jobs/{job_id}/events") as stream:
        assert stream.headers["content-type"].startswith("text/event-stream")
        name = None
        for line in stream.iter_lines():
            if line.startswith("event:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                events.append((name, json.loads(line.split(":", 1)[1])))
    assert events[-1][0] == "end" and events[-1][1]["state"] == "done"
    assert events[-1][1]["progress"] == {"ply": 7, "total": 7}
    assert all(e[0] in ("progress", "end") for e in events)


def test_pgn_file_upload_as_raw_body(client):
    response = client.post("/api/analyze/pgn?seconds=0.1&perspective=white", content=SCHOLAR.encode())
    assert response.status_code == 202
    assert wait_for(client, response.json()["job_id"])["state"] == "done"


def test_several_games_report_combined_progress(client):
    job_id = analyse(client, SCHOLAR + "\n" + FOOL)
    job = wait_for(client, job_id)
    assert job["progress"] == {"ply": 11, "total": 11}
    games = client.get(f"/api/annotations/{job_id}").json()["games"]
    assert [g["game"] for g in games] == [1, 2] and games[1]["headers"]["Event"] == "Fool's Mate"


def test_fen_position_analysis(client):
    fen = "rnbqkbnr/pppp1ppp/8/4p3/6P1/5P2/PPPPP2P/RNBQKBNR b KQkq - 0 2"
    response = client.post("/api/analyze", json={"fen": fen})
    job = wait_for(client, response.json()["job_id"])
    assert job["state"] == "done" and job["source"] == "fen"
    body = client.get(f"/api/annotations/{job['job_id']}").json()
    assert body["position"]["lines"][0]["best_move_san"] == "Qh4#"
    assert client.get(f"/api/report/{job['job_id']}").status_code == 422


def test_filtered_perspective_still_serves_every_board_position(client):
    job_id = analyse(client, perspective="black")
    wait_for(client, job_id)
    moves = client.get(f"/api/annotations/{job_id}").json()["games"][0]["moves"]
    assert [m["ply"] for m in moves] == [2, 4, 6]
    assert all(m["fen_before"] and m["fen_after"] for m in moves)      # replayed from the PGN


# --- busy, never hanging -------------------------------------------------------

def test_second_analysis_while_one_runs_is_busy_immediately(tmp_path):
    gate = threading.Event()
    client = make_client(tmp_path, engine=FakeEngine(gate))
    first = analyse(client)
    started = time.monotonic()
    second = client.post("/api/analyze", json={"pgn_text": FOOL}).json()
    assert second["state"] == "busy" and time.monotonic() - started < 1
    busy = client.get(f"/api/jobs/{second['job_id']}").json()
    assert busy["state"] == "busy" and busy["error"]["type"] == "busy"
    assert client.get(f"/api/annotations/{second['job_id']}").status_code == 409
    gate.set()
    assert wait_for(client, first)["state"] == "done"
    assert wait_for(client, analyse(client, FOOL))["state"] == "done"      # capacity is back


def test_slot_held_by_another_process_gives_busy_not_a_hang(tmp_path):
    client = make_client(tmp_path, queue_timeout=0.2)
    with job_slot(tmp_path, max_jobs=1, queue_timeout=0):                  # e.g. the CLI is running
        started = time.monotonic()
        job = wait_for(client, analyse(client))
        assert job["state"] == "busy" and time.monotonic() - started < 3
        assert "busy" in job["error"]["message"].lower()
    assert wait_for(client, analyse(client))["state"] == "done"


# --- input validation and caps -------------------------------------------------

@pytest.mark.parametrize("payload, kind", [
    ({"pgn_text": "1. e4 e5 2. Ke4 *"}, "invalid_input"),                  # illegal move
    ({"pgn_text": "not a pgn at all"}, "invalid_input"),
    ({"pgn_text": SCHOLAR, "fen": "8/8/8/8/8/8/8/8 w - - 0 1"}, "invalid_input"),
    ({}, "invalid_input"),
    ({"fen": "nonsense"}, "invalid_input"),
    ({"pgn_text": SCHOLAR, "seconds": 5}, "invalid_input"),
    ({"pgn_text": SCHOLAR, "seconds": 0}, "invalid_input"),
    ({"pgn_text": SCHOLAR, "multipv": 9}, "invalid_input"),
    ({"pgn_text": SCHOLAR, "perspective": "green"}, "invalid_input"),
    ({"pgn_text": SCHOLAR, "surprise": 1}, "invalid_input"),
])
def test_invalid_input_is_a_clean_422(client, payload, kind):
    response = client.post("/api/analyze", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["type"] == kind and response.json()["error"]["message"]


def test_malformed_json_is_a_clean_422(client):
    response = client.post("/api/analyze", content=b"{nope", headers={"content-type": "application/json"})
    assert response.status_code == 422 and response.json()["error"]["type"] == "invalid_input"


def test_oversized_inputs_are_rejected_before_any_engine_work(client):
    huge = "[Event \"x\"]\n\n" + "{" + "x" * (web_app.MAX_PGN_BYTES + 10) + "} 1. e4 *"
    assert client.post("/api/analyze", json={"pgn_text": huge}).status_code == 413
    assert client.post("/api/analyze", content=b"x" * (web_app.MAX_BODY_BYTES + 1),
                       headers={"content-type": "application/json"}).status_code == 413
    assert client.post("/api/analyze/pgn", content=b"x" * (web_app.MAX_PGN_BYTES + 1)).status_code == 413
    assert client.post("/api/analyze/pgn", content=b"\xff\xfe\xfa").status_code == 422     # not UTF-8


def test_game_ply_and_time_caps(client):
    assert client.post("/api/analyze", json={"pgn_text": (SCHOLAR + "\n") * 4}).json()["error"]["type"] == "too_many_games"
    moves = [f"{i}. " + ("Nf3 Nf6" if i % 2 else "Ng1 Ng8") for i in range(1, 102)]
    long_game = " ".join(moves) + " *"                                      # 202 plies
    capped = client.post("/api/analyze", json={"pgn_text": long_game})
    assert capped.status_code == 422 and capped.json()["error"]["type"] == "too_many_plies"
    moves = [f"{i}. " + ("Nf3 Nf6" if i % 2 else "Ng1 Ng8") for i in range(1, 100)]
    slow = client.post("/api/analyze", json={"pgn_text": " ".join(moves) + " *", "seconds": 2})
    assert slow.status_code == 422 and slow.json()["error"]["type"] == "too_expensive"


# --- lookups and locales -------------------------------------------------------

def test_unknown_job_unknown_locale_and_not_ready(client):
    assert client.get("/api/jobs/nope").status_code == 404
    job_id = analyse(client)
    wait_for(client, job_id)
    for path in ("annotations", "report"):
        bad = client.get(f"/api/{path}/{job_id}?locale=xx")
        assert bad.status_code == 422 and bad.json()["error"]["type"] == "unknown_locale"
        assert client.get(f"/api/{path}/{job_id}?locale=../x").status_code == 422
        assert client.get(f"/api/{path}/{job_id}?locale=en-GB").status_code == 200   # base language
    assert client.get(f"/api/report/{job_id}?player=green").status_code == 422
    assert client.get(f"/api/report/{job_id}?max_chars=10").status_code == 422


def test_locales_lists_every_catalog(client):
    codes = [item["code"] for item in client.get("/api/locales").json()["locales"]]
    assert "en" in codes and codes == sorted(codes)


# --- the explanation layer, seen from HTTP -------------------------------------

def check_rendered(moves):
    emitted = set()
    for move in moves:
        for annotation in move["annotations"]:
            emitted.add(annotation["key"])
            text = annotation["text"]
            assert annotation["key"] in KEYS and isinstance(annotation["params"], dict)
            assert text.strip() and "explain." not in text and not re.search(r"\{\w+\}", text), annotation
    return emitted


def test_every_raw_key_the_api_emits_comes_with_a_rendered_sentence(client):
    emitted = set()
    for pgn in (SCHOLAR, FOOL, "[Event \"Hung\"]\n\n1. e4 e5 2. Nf3 Nc6 3. Nxe5 Nxe5 4. d4 Nc6 *\n"):
        job_id = analyse(client, pgn)
        wait_for(client, job_id)
        body = client.get(f"/api/annotations/{job_id}").json()
        emitted |= check_rendered(m for g in body["games"] for m in g["moves"])
    assert {"allowed_mate", "terminal_checkmate", "engine_preferred", "best_move"} <= emitted


def test_real_engine_fixtures_render_every_emitted_key(tmp_path):
    """Pre-analysed real Stockfish output injected as finished jobs (no engine needed)."""
    client = make_client(tmp_path)
    manager = client.app.state.jobs
    emitted = set()
    for name in ("two_games", "long_game"):
        result = load_fixture(name)
        games = parse_pgn((DATA / f"{name}.pgn").read_text())
        job = Job(id=f"fixture-{name}", request=JobRequest("pgn", AnalysisConfig(), games=games),
                  state="done", result=result)
        manager._jobs[job.id] = job
        body = client.get(f"/api/annotations/{job.id}").json()
        emitted |= check_rendered(m for g in body["games"] for m in g["moves"])
        assert client.get(f"/api/report/{job.id}").json()["text"].startswith(("Game", "♟"))
    assert {"book_move", "left_book", "allowed_mate", "terminal_checkmate"} <= emitted


# --- the page itself -----------------------------------------------------------

def test_page_and_vendored_board_are_served_with_a_content_security_policy(client):
    page = client.get("/")
    assert page.status_code == 200 and "text/html" in page.headers["content-type"]
    assert "script-src 'self'" in page.headers["content-security-policy"]
    script = client.get("/static/vendor/cm-chessboard/src/Chessboard.js")
    assert script.status_code == 200 and "javascript" in script.headers["content-type"]
    assert client.get("/static/vendor/cm-chessboard/assets/pieces/standard.svg").status_code == 200
    assert client.get("/static/../app.py").status_code in (404, 400)


def test_frontend_has_no_absolute_urls_and_no_cdn():
    root = Path(web_app.__file__).parent / "static"
    files = [p for p in root.rglob("*") if p.suffix in (".html", ".js", ".css") and "vendor" not in p.parts]
    assert files
    for path in files:
        text = path.read_text(encoding="utf-8").replace("http://www.w3.org/2000/svg", "")  # SVG XML namespace id, never fetched
        assert not re.search(r"https?://", text), path
        assert not re.search(r"""(?:src|href)=["']/|fetch\(["'`]/|url\(["']?/""", text), path
    licence = root / "vendor/cm-chessboard/LICENSE"
    assert "MIT License" in licence.read_text()


@pytest.mark.skipif(not Path(default_engine()).exists(), reason="Stockfish not installed")
def test_real_stockfish_through_the_web_api(tmp_path):
    app = web_app.create_app(lock_dir=tmp_path, queue_timeout=0.5)
    client = TestClient(app)
    job_id = analyse(client, FOOL, seconds=0.05)
    assert wait_for(client, job_id, timeout=60)["state"] == "done"
    moves = client.get(f"/api/annotations/{job_id}").json()["games"][0]["moves"]
    assert moves[-1]["annotations"][0]["key"] == "terminal_checkmate"


def test_old_finished_jobs_are_evicted_but_a_running_job_never_is(tmp_path):
    client = make_client(tmp_path)
    manager = client.app.state.jobs
    manager.keep = 2
    ids = []
    for _ in range(3):
        ids.append(analyse(client, FOOL))
        wait_for(client, ids[-1])
    assert client.get(f"/api/jobs/{ids[0]}").status_code == 404          # evicted
    assert client.get(f"/api/jobs/{ids[2]}").status_code == 200
    gate = threading.Event()
    slow = make_client(tmp_path, engine=FakeEngine(gate))
    slow.app.state.jobs.keep = 1
    running = analyse(slow, FOOL)
    busy = slow.post("/api/analyze", json={"pgn_text": FOOL}).json()["job_id"]   # a second entry: over `keep`
    assert slow.get(f"/api/jobs/{running}").status_code == 200           # still running, not evicted
    assert slow.get(f"/api/jobs/{busy}").status_code == 200
    gate.set()
    wait_for(slow, running)


def test_server_entry_point_defaults_to_loopback_and_warns_otherwise(monkeypatch, capsys):
    from web import __main__ as entry
    calls = []
    monkeypatch.setattr(entry.uvicorn, "run", lambda app, **kw: calls.append(kw))
    monkeypatch.delenv("CHESS_WEB_HOST", raising=False)
    assert entry.main([]) == 0
    assert calls[-1]["host"] == "127.0.0.1" and calls[-1]["port"] == 8765
    assert "warning" not in capsys.readouterr().err
    entry.main(["--host", "0.0.0.0", "--port", "9000"])
    assert calls[-1]["host"] == "0.0.0.0" and "no authentication" in capsys.readouterr().err
