// cm-chessboard (MIT, vendored) with its arrows extension. The sprites are located relative
// to this module, so no absolute path or CDN is involved.
import { Chessboard, COLOR, FEN } from "./vendor/cm-chessboard/src/Chessboard.js";
import { Arrows, ARROW_TYPE } from "./vendor/cm-chessboard/src/extensions/arrows/Arrows.js";

export const START = FEN.start;

export function createBoard(element) {
  const board = new Chessboard(element, {
    position: FEN.start,
    assetsUrl: new URL("vendor/cm-chessboard/assets/", import.meta.url).href,
    style: { cssClass: "default", showCoordinates: true, animationDuration: 120 },
    extensions: [{ class: Arrows }],
  });
  let flipped = false;
  return {
    show(fen, arrows = []) {
      board.setPosition(fen, false);
      board.removeArrows();
      for (const [type, squares] of arrows) {
        if (squares) board.addArrow(ARROW_TYPE[type], squares.from, squares.to);
      }
    },
    flip() {
      flipped = !flipped;
      board.setOrientation(flipped ? COLOR.black : COLOR.white, false);
    },
  };
}
