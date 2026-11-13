"""FastAPI backend for the local inspection UI. It imports chess_backend directly:
no subprocess, no outbound network, and the same host-wide engine slot as the CLI."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from chess_backend.analysis import AnalysisConfig, Analyzer
from chess_backend.cli import ROOT, default_engine
from chess_backend.inputs import InputError, parse_fen, parse_pgn
from chess_backend.narration import render_report

from .jobs import TERMINAL, Job, JobManager, JobRequest
from .views import available_locales, build_annotations, is_known_locale, position_view

STATIC = Path(__file__).parent / "static"
# Input caps, kept from the start because the server may be exposed beyond localhost later.
# Seconds go up to 2 per position, which suits local use.
MAX_PGN_BYTES = 512 * 1024
MAX_BODY_BYTES = 1024 * 1024               # a JSON-encoded PGN is a little larger than the PGN
MAX_GAMES = 3
MAX_TOTAL_PLIES = 200
MAX_SECONDS = 2.0
MAX_JOB_SECONDS = 300.0                    # estimated engine time for one job
CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
       "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")


class ApiError(Exception):
    def __init__(self, status: int, kind: str, message: str):
        super().__init__(message)
        self.status, self.kind, self.message = status, kind, message


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pgn_text: str | None = None
    fen: str | None = None
    seconds: float = Field(0.3, ge=0.01, le=MAX_SECONDS)
    multipv: int = Field(1, ge=1, le=5)
    perspective: Literal["both", "white", "black"] = "both"


async def read_body(request: Request, limit: int) -> bytes:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise ApiError(413, "too_large", f"request body is larger than {limit} bytes")
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise ApiError(413, "too_large", f"request body is larger than {limit} bytes")
        chunks.append(chunk)
    return b"".join(chunks)


def build_job_request(*, pgn_text: str | None, fen: str | None, seconds: float, multipv: int,
                      perspective: str) -> JobRequest:
    if (pgn_text is None) == (fen is None):
        raise ApiError(422, "invalid_input", "supply exactly one of pgn_text or fen")
    try:
        config = AnalysisConfig(seconds=seconds, multipv=multipv, perspective=perspective)
    except ValueError as exc:
        raise ApiError(422, "invalid_input", str(exc)) from exc
    if fen is not None:
        try:
            return JobRequest("fen", config, board=parse_fen(fen))
        except InputError as exc:
            raise ApiError(422, "invalid_input", str(exc)) from exc
    if len(pgn_text.encode("utf-8")) > MAX_PGN_BYTES:
        raise ApiError(413, "too_large", f"PGN is larger than {MAX_PGN_BYTES} bytes")
    try:
        games = parse_pgn(pgn_text)
    except InputError as exc:
        raise ApiError(422, "invalid_input", f"invalid or illegal PGN: {exc}") from exc
    if len(games) > MAX_GAMES:
        raise ApiError(422, "too_many_games", f"too many games: maximum {MAX_GAMES} per analysis")
    request = JobRequest("pgn", config, games=games)
    if request.total_plies == 0:
        raise ApiError(422, "invalid_input", "the PGN contains no moves to analyse")
    if request.total_plies > MAX_TOTAL_PLIES:
        raise ApiError(422, "too_many_plies", f"too many plies: maximum {MAX_TOTAL_PLIES} per analysis")
    if (request.total_plies + len(games)) * seconds > MAX_JOB_SECONDS:
        raise ApiError(422, "too_expensive",
                       f"this would take more than {MAX_JOB_SECONDS:g} s; lower seconds or analyse fewer plies")
    return request


def create_app(*, engine_path: Path | None = None, lock_dir: Path | None = None,
               queue_timeout: float = 2.0, analyzer_factory=None) -> FastAPI:
    engine = Path(engine_path) if engine_path else default_engine()
    factory = analyzer_factory or (lambda cfg: Analyzer(engine, cfg))
    manager = JobManager(factory, lock_dir or ROOT / "data", queue_timeout=queue_timeout)
    app = FastAPI(title="Chess analyzer inspector", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.jobs = manager

    # ---- errors in the same shape as the JSON CLI: {"error": {"type", "message"}} ----
    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError):
        return JSONResponse({"error": {"type": exc.kind, "message": exc.message}}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def invalid_query(_: Request, exc: RequestValidationError):
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first["loc"] if p != "query")
        return JSONResponse({"error": {"type": "invalid_input", "message": f"{where}: {first['msg']}"}},
                            status_code=422)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("Content-Security-Policy", CSP)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    def job_or_404(job_id: str) -> Job:
        job = manager.get(job_id)
        if job is None:
            raise ApiError(404, "not_found", "unknown job")
        return job

    def finished_pgn_job(job_id: str) -> Job:
        job = job_or_404(job_id)
        if job.state != "done":
            raise ApiError(409, "not_ready", f"job is {job.state}")
        if job.request.source != "pgn":
            raise ApiError(422, "invalid_input", "only PGN analyses have per-move annotations")
        return job

    def locale_or_422(locale: str) -> str:
        if not is_known_locale(locale):
            have = ", ".join(item["code"] for item in available_locales())
            raise ApiError(422, "unknown_locale", f"unknown locale {locale[:20]!r}; available: {have}")
        return locale

    # ---- API ----
    @app.post("/api/analyze", status_code=202)
    async def analyze(request: Request):
        body = await read_body(request, MAX_BODY_BYTES)
        try:
            data = AnalyzeRequest.model_validate_json(body)
        except ValidationError as exc:
            first = exc.errors()[0]
            raise ApiError(422, "invalid_input", f"{'.'.join(map(str, first['loc'])) or 'body'}: {first['msg']}") from exc
        job = manager.submit(build_job_request(**data.model_dump()))
        return {"job_id": job.id, "state": job.state}

    @app.post("/api/analyze/pgn", status_code=202)
    async def analyze_upload(request: Request, seconds: float = Query(0.3, ge=0.01, le=MAX_SECONDS),
                             multipv: int = Query(1, ge=1, le=5),
                             perspective: Literal["both", "white", "black"] = "both"):
        """PGN file upload as the raw request body (curl --data-binary @game.pgn)."""
        raw = await read_body(request, MAX_PGN_BYTES)
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ApiError(422, "invalid_input", "PGN must be UTF-8 text") from exc
        job = manager.submit(build_job_request(pgn_text=text, fen=None, seconds=seconds,
                                               multipv=multipv, perspective=perspective))
        return {"job_id": job.id, "state": job.state}

    @app.get("/api/jobs/{job_id}")
    async def job_state(job_id: str):
        return job_or_404(job_id).snapshot()

    @app.get("/api/jobs/{job_id}/events")
    async def job_events(job_id: str):
        job = job_or_404(job_id)

        async def stream():
            last, beat = None, time.monotonic()
            while True:
                snapshot = json.dumps(job.snapshot())
                if snapshot != last:
                    yield f"event: progress\ndata: {snapshot}\n\n"
                    last = snapshot
                if job.state in TERMINAL:
                    yield f"event: end\ndata: {snapshot}\n\n"
                    return
                if time.monotonic() - beat > 10:
                    yield ": keepalive\n\n"
                    beat = time.monotonic()
                await asyncio.sleep(0.15)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/annotations/{job_id}")
    async def annotations(job_id: str, locale: str = "en"):
        locale_or_422(locale)
        job = job_or_404(job_id)
        if job.state == "done" and job.request.source == "fen":
            return {"job_id": job_id, "source": "fen", "position": position_view(job.result)}
        job = finished_pgn_job(job_id)
        return {"job_id": job_id, "source": "pgn", **build_annotations(job.result, job.request.games, locale)}

    @app.get("/api/report/{job_id}")
    async def report(job_id: str, locale: str = "en", player: Literal["both", "white", "black"] = "both",
                     max_chars: int = Query(3500, ge=300, le=3900)):
        locale_or_422(locale)
        job = finished_pgn_job(job_id)
        text = render_report(job.result, player=player, max_chars=max_chars, locale=locale)
        return {"job_id": job_id, "locale": locale, "player": player, "text": text}

    @app.get("/api/locales")
    async def locales():
        return {"locales": available_locales()}

    # ---- UI ----
    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
