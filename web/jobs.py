"""Analysis jobs for the web UI: one at a time per process, and the host-wide
Stockfish slot (limits.job_slot) is honoured so the CLI and this server never
run more engines than configured."""
from __future__ import annotations

import logging
import secrets
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import chess
import chess.pgn

from chess_backend.analysis import AnalysisConfig, Analyzer, EngineFailure
from chess_backend.limits import BusyError, job_slot

log = logging.getLogger(__name__)
TERMINAL = ("done", "failed", "busy")


@dataclass
class JobRequest:
    source: str                                  # "pgn" or "fen"
    config: AnalysisConfig
    games: list[chess.pgn.Game] = field(default_factory=list)
    board: chess.Board | None = None

    @property
    def total_plies(self) -> int:
        return sum(len(list(game.mainline_moves())) for game in self.games) if self.source == "pgn" else 1


@dataclass
class Job:
    id: str
    request: JobRequest
    state: str = "queued"                        # queued | running | done | failed | busy
    ply: int = 0
    total: int = 0
    error: dict | None = None
    result: dict | None = None

    def snapshot(self) -> dict:
        out = {"job_id": self.id, "state": self.state, "source": self.request.source,
               "progress": {"ply": self.ply, "total": self.total}}
        if self.error:
            out["error"] = self.error
        return out


class JobManager:
    def __init__(self, analyzer_factory: Callable[[AnalysisConfig], Analyzer], lock_dir: Path,
                 *, queue_timeout: float = 2.0, keep: int = 20):
        self.analyzer_factory = analyzer_factory
        self.lock_dir = Path(lock_dir)
        self.queue_timeout = queue_timeout
        self.keep = keep
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def submit(self, request: JobRequest) -> Job:
        job = Job(id=secrets.token_urlsafe(8), request=request, total=request.total_plies)
        with self._lock:
            if any(j.state in ("queued", "running") for j in self._jobs.values()):
                job.state = "busy"               # never queue behind another job: answer at once
                job.error = {"type": "busy", "message": "another analysis is already running"}
            self._jobs[job.id] = job
            self._evict(keep_id=job.id)
        if job.state == "queued":
            threading.Thread(target=self._run, args=(job,), name=f"analysis-{job.id}", daemon=True).start()
        return job

    def _evict(self, keep_id: str) -> None:
        """Drop the oldest finished jobs beyond `keep`; never a running one or the newest."""
        while len(self._jobs) > self.keep:
            oldest = next((j for j in self._jobs.values() if j.state in TERMINAL and j.id != keep_id), None)
            if oldest is None:
                return
            del self._jobs[oldest.id]

    def _run(self, job: Job) -> None:
        try:
            with job_slot(self.lock_dir, max_jobs=1, queue_timeout=self.queue_timeout):
                job.state = "running"
                job.result = self._analyse(job)
            job.state = "done"
        except BusyError as exc:
            job.state, job.error = "busy", {"type": "busy", "message": str(exc)}
        except EngineFailure as exc:
            job.state, job.error = "failed", {"type": "engine_failure", "message": str(exc)}
        except (ValueError, OSError, UnicodeError) as exc:
            job.state, job.error = "failed", {"type": "invalid_input", "message": str(exc)}
        except Exception:                        # noqa: BLE001 - a worker must never die silently
            log.exception("analysis job %s crashed", job.id)
            job.state, job.error = "failed", {"type": "internal_error", "message": "analysis crashed"}

    def _analyse(self, job: Job) -> dict:
        request, cfg = job.request, job.request.config
        with self.analyzer_factory(cfg) as analyzer:
            if request.source == "pgn":
                done, games = 0, []              # `done` = plies finished in earlier games
                for number, game in enumerate(request.games, 1):
                    games.append(analyzer.analyze_game(
                        game, number=number,
                        progress=lambda ply, _total, base=done: setattr(job, "ply", base + ply)))
                    done += len(list(game.mainline_moves()))
                payload = {"games": games}
            else:
                payload = {"position": analyzer.analyze_position(request.board)}
                job.ply = 1
        # Same envelope as the JSON CLI, so the narration and explain layers can consume it.
        return {"ok": True, "source": request.source,
                "engine": {"name": "Stockfish UCI", "threads": cfg.threads, "hash_mb": cfg.hash_mb,
                           "seconds_per_position": cfg.seconds, "multipv": cfg.multipv},
                "perspective": cfg.perspective, "thresholds_cp": cfg.thresholds.to_dict(), **payload}
