# Vendored front-end code

`cm-chessboard/` is [cm-chessboard](https://github.com/shaack/cm-chessboard) 8.15.4 by Stefan
Haack, copied unmodified from the npm package (`npm pack cm-chessboard@8.15.4`): `src/` plus the
compiled CSS and the piece and arrow sprites from `assets/` (SCSS sources and source maps are
left out). It is served from this app, so the UI works offline; there is no CDN at runtime.
chessground (GPL-3.0) is deliberately not used.

## Licences

- The library code (`cm-chessboard/src/`, `assets/*.css`) is **MIT** (`cm-chessboard/LICENSE`).
- The piece sprite `cm-chessboard/assets/pieces/standard.svg` is **not** MIT. Its own header says
  *Attribution-ShareAlike 3.0 Unported (CC BY-SA 3.0)* and points to the Wikimedia Commons
  "SVG chess pieces / Standard" set; cm-chessboard's README says the same. The header is kept in
  the file as the attribution.
- `cm-chessboard/assets/extensions/arrows/arrows.svg` carries no separate licence notice.
- The marker shapes are our own `web/static/markers.svg` (a plain square), so the CC BY-SA
  marker sprite from the package is not included.

This is a description of the notices in the files, not legal advice.
