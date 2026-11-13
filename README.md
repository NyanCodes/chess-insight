# chess-insight

Analyses chess games with Stockfish and explains each mistake in plain words. It runs entirely on your machine: no chess website, no API key, no AI service. Classifications and explanations come from Stockfish's output plus fixed, deterministic rules, so the same game always reads the same way.

## Quick start

```bash
git clone https://github.com/NyanCodes/chess-insight.git
cd chess-insight
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
```

You also need the Stockfish engine (see below). Then check everything works:

```bash
.venv/bin/python -m pytest tests -q
```

All 113 tests should pass. If the engine is missing, the engine-dependent tests are the ones that fail or are skipped.

### Getting Stockfish

Either install it with your package manager:

```bash
sudo pacman -S stockfish      # Arch
sudo apt install stockfish    # Debian/Ubuntu
brew install stockfish        # macOS
```

Or download the official binary into `bin/`, which needs no admin rights:

```bash
curl -L -o /tmp/sf.tar.gz \
  https://github.com/official-stockfish/Stockfish/releases/download/sf_19/stockfish-linux-x86-64-universal.tar.gz
tar -xzf /tmp/sf.tar.gz -C /tmp
cp /tmp/stockfish/stockfish-linux-x86-64-universal bin/
chmod +x bin/stockfish-linux-x86-64-universal
```

The analyzer looks for `bin/stockfish-linux-x86-64-universal` first, then `stockfish` on your `PATH`. `--engine /path/to/stockfish` overrides both. Stockfish is not part of this repository and is licensed separately (GPL-3.0).

### Three ways to use it

A browser inspector: the board, the move list, and the reason behind each classification side by side.

```bash
.venv/bin/python -m web      # then open http://127.0.0.1:8765/
```

Paste a PGN or press **Load sample**, then click any move. The green arrow is the engine's choice, orange is what was played.

A readable game story, printed in the terminal (the JSON CLI's output piped into the narration):

```bash
.venv/bin/python -m chess_backend --pgn-file tests/data/two_games.pgn --seconds 0.3 --multipv 1 \
  | .venv/bin/python -m chess_backend.narrate --player both
```

Raw JSON, one object per invocation, for scripting:

```bash
.venv/bin/python analyze.py --pgn-text '1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7# 1-0' --seconds 0.3
.venv/bin/python -m chess_backend --fen 'rnbqkbnr/pppp1ppp/8/4p3/6P1/5P2/PPPPP2P/RNBQKBNR b KQkq - 0 2' --seconds 1 --multipv 3
```

Analysis time is roughly `seconds` x number of plies, so start small: 0.3 seconds per position is enough to spot blunders in a full game. `analyze.py` and `python -m chess_backend` are interchangeable JSON entry points. `requirements.txt` holds the runtime dependencies; `requirements-dev.txt` adds the test tools.

## Inputs and outputs

Exactly one of `--pgn-file`, `--pgn-text`, or `--fen` may be supplied. Without one, analyze the starting position; optional `--moves` applies SAN/UCI moves to a FEN or starting position. PGN input analyzes **all games and all plies** (the main line), not just the first game's final position. Invalid FEN, bad/illegal PGN moves, and illegal `--moves` yield JSON with `ok:false`, `error.type:"invalid_input"`, exit status 2. Engine startup/crash/timeout yields `engine_failure`, status 3; capacity contention yields `busy`, status 4. Successful calls yield `ok:true`, status 0. Output is one compact JSON object per invocation.

PGN results contain `games` with headers, result, ply count, `moves`, and `critical_plies`. Each reported move includes played/best SAN+UCI, truncated best PV, evaluation before/after, mover-relative `cp_loss`, and local classification. FEN results contain `position.lines` with best move, PV, and evaluation. `--perspective white|black|both` filters reported *game moves*, not the engine's calculations; FEN output retains the side to move. `evaluation.cp_white` and `mate_white` are **always White's perspective**: positive favors White, negative favors Black; `mate_white` is an engine mate distance, not a centipawn score. `eval_after` is null on terminal positions and `terminal_result` supplies the outcome.

## Local classification policy (not a website accuracy score)

When both scores are centipawns, `cp_loss = max(0, best-evaluation-before - played-evaluation-after)` from **the mover's perspective**. Values are approximate because the engine searches different positions at finite time/depth. A move matching the engine's top move has zero loss even if search scores drift. Defaults (inclusive): **inaccuracy ≥50 cp**, **mistake ≥100 cp**, **blunder ≥250 cp**; customize with `--thresholds 40,90,180`. Smaller losses are `none`. If either score is a forced-mate score, `cp_loss` is `null`: dropping a winning mate or walking into a forced mate is `blunder`; changed mate distances otherwise receive `unclassified_mate` rather than a fictitious centipawn value. `critical_plies` lists mistakes and blunders. The narration treats a move as **theory** while its line is a prefix of a named opening line (so a main-line move without a name of its own, like 4. Ba4 in the Ruy Lopez, stays in theory), reporting the most specific name reached. Theory stops at the first move outside the database, or at the first move the engine flags as an inaccuracy or worse, which is then reported as an error and never as a graded book move. Engine-detected errors are always counted, whatever the opening database says. Uncertain mate-distance changes are described as hard to judge. Great and Brilliant are deliberately not auto-awarded: the short search and one best line cannot establish the uniqueness and sound sacrifice required for those claims. Opening names come from a pinned CC0 Lichess dataset (`chess_backend/openings_data/README.md`), matched by exact SAN prefix; unknown lines and transpositions are not guessed. These are our transparent local heuristics, **not official Chess.com/Lichess accuracy or classifications**. Interpret short searches cautiously.

## Resource limits

Defaults: Stockfish **Threads=2**, **Hash=256 MB**, `--seconds 2` per position, `--multipv 2`, at most **one concurrent job** across CLI processes on this machine. `--max-jobs 2` permits a second slot (upper bound two), and `--queue-timeout 10` controls waiting for a slot. Slots use POSIX file locks in `data/`; they release on normal exit or process death. Higher job limits consume additional CPU/RAM. Full games analyze one engine process and approximately one search per position, so long PGNs at 2 seconds/position can take minutes. `--seconds` is capped at 20; `--threads` at 4; `--hash-mb` at 1024. A python-chess UCI communication timeout bounds hung searches beyond the per-position budget. No global time limit for an entire PGN is imposed.

## Explanations and languages

The story is built in three layers so that no sentence is ever assembled from fragments in code:

- `chess_backend/explain/` reads the analysis JSON, replays the game with python-chess and emits **structured annotations only**, for example `{"key": "hung_piece", "params": {"piece": "knight", "square": "e5", "captured_by": "Nxe5", "cp": 280}}`. The taxonomy is in `explain/schema.py` (16 keys). Rules use only engine data: material across the played move and the engine's reply line (taken from the opponent's next row, so a `--perspective`-filtered result simply explains less), the engine's best line, mate scores and `cp_loss`. It never names tactical motifs or positional themes, and it contains no user-facing English (a test scans the code for it). No AI model is involved anywhere.
- `chess_backend/i18n/` renders annotations through `locales/<code>.json`. Every entry is a whole sentence with named placeholders; counting entries are plural objects keyed by CLDR category (`one`/`other` for English, `other` alone for Burmese). Lookup falls back from region to base language to `en` to the key itself, and numbers go through one helper (`format_number`).
- `chess_backend/narration.py` chooses which sentences apply and fits them into the character budget.

To add a language, copy `i18n/locales/en.json` to e.g. `my.json`, translate the values (keep the keys and `{placeholders}`), and pass `locale="my"` to `render_report`. `tests/test_catalog_coverage.py` fails if a key emitted by `explain/` is missing from `en.json` or if `en.json` holds a key nothing can reach; run it after changing either side.

## Web UI

A local page for inspecting the explanation and translation layers: the board with the engine's best-move arrow, an evaluation bar and graph, one row per ply, and, for the selected move, the rendered sentences, the raw `{key, params}` behind them and the engine numbers, side by side. A narration panel at the bottom has a language dropdown fed by the available catalogs.

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m web            # then open http://127.0.0.1:8765/
.venv/bin/python -m web --host 127.0.0.1 --port 8765   # or CHESS_WEB_HOST / CHESS_WEB_PORT
```

It binds to localhost by default (configurable; binding elsewhere prints a warning: there is no authentication or rate limiting yet). The backend imports `chess_backend` directly, makes no outbound network calls, serves everything itself (cm-chessboard is vendored under `web/static/vendor/`, MIT, no CDN) and uses only relative URLs, so it also works behind a path prefix. One analysis runs at a time and honours the same host-wide Stockfish slot as the CLI; a second request gets state `busy` at once instead of waiting.

| Endpoint | Purpose |
| --- | --- |
| `POST /api/analyze` | JSON with `pgn_text` or `fen`, plus `seconds` (0.01..2, default 0.3), `multipv` (1..5), `perspective`; returns `{job_id, state}` (202) |
| `POST /api/analyze/pgn?seconds=&multipv=&perspective=` | the PGN file as the raw request body (`curl --data-binary @game.pgn`) |
| `GET /api/jobs/{id}` | `{state, progress: {ply, total}, error?: {type, message}}`; state is `queued`, `running`, `done`, `failed` or `busy` |
| `GET /api/jobs/{id}/events` | server-sent events: `progress` and a final `end` |
| `GET /api/annotations/{id}?locale=en` | per move: SAN, classification, engine numbers (White- and mover-relative), FENs and arrow squares, and every annotation as raw `{key, params}` plus rendered `text` |
| `GET /api/report/{id}?locale=en&player=both&max_chars=3500` | the plain-language narration |
| `GET /api/locales` | available catalogs |

Errors use the CLI's shape, `{"error": {"type", "message"}}`. Input caps: 512 KB of PGN, 3 games, 200 plies, plus an estimated-time cap of 300 s per job. An unknown locale is a 422 (a regional code such as `en-GB` falls back to its base language). Jobs live in memory (the last 20); nothing is written to disk.

`Analyzer.analyze_game` accepts an optional `progress(ply, total_plies)` callback, used for the progress bar. It never changes the result: `tests/test_progress_callback.py` compares the serialised JSON with and without it.
