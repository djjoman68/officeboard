"""Panel test: colour bars and a line of scrolling text with the live frame rate.

For checking the new P3 panel (every colour lights, nothing swapped, no dead rows) and for judging
how smooth scrolling looks on the real LEDs before the scroll experiment in step 3.
"""
from core import pixels
from core.module import Module

# Pure colours, so a dead or swapped red, green or blue channel is obvious
BARS = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255),
        (255, 255, 0), (0, 255, 255), (255, 0, 255), (128, 128, 128)]


class PanelTest(Module):
    id = "paneltest"
    name = "Panel test"
    description = "Colour bars and scrolling text with the frame rate. For checking the panel."
    default_enabled = True
    default_seconds = 20
    fields = [
        {"key": "message", "label": "Scrolling text", "type": "text", "default": "OFFICE BOARD",
         "hint": "Any text, to see how it reads when it scrolls."},
    ]

    def __init__(self, board=None):
        super().__init__(board)
        self._strip_key = None
        self._strip = None

    def _ticker(self):
        fps = round(self.board.fps)
        key = (self.settings["message"], fps)
        if key != self._strip_key:
            pieces = [(self.settings["message"] + "   ", pixels.WHITE)]
            if fps:
                pieces.append((f"{fps} FPS   ", pixels.YELLOW))
            self._strip = pixels.text_strip("regular", pieces, 12)
            self._strip_key = key
        return self._strip

    def frame(self, now, t):
        img = pixels.blank()
        title = "PANEL TEST"
        pixels.draw_text(img, "small", (64 - pixels.text_width("small", title)) // 2, 7, pixels.WHITE, title)
        for i, colour in enumerate(BARS):
            img.paste(colour, (i * 8, 9, i * 8 + 8, 17))
        return pixels.marquee(img, self._ticker(), t, self.board.display["scroll_speed"], y=19)
