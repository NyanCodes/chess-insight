# Vendored front-end code

`cm-chessboard/` is [cm-chessboard](https://github.com/shaack/cm-chessboard) 8.15.4 by Stefan
Haack, **MIT licensed** (see `cm-chessboard/LICENSE`), copied unmodified from the npm package
(`npm pack cm-chessboard@8.15.4`): `src/` plus the compiled CSS and the piece and arrow sprites
from `assets/` (SCSS sources and source maps are left out). It is served from this app, so the
UI works offline; there is no CDN at runtime. chessground (GPL-3.0) is deliberately not used.
