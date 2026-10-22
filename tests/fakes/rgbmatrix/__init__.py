"""Stand-in for the rgbmatrix panel library so the display loop can run on any computer (tests only).
From itsposttime. Modified for the office board: counts swaps so tests can see what reached the panel."""
from PIL import Image
from . import graphics  # noqa: F401


class RGBMatrixOptions:
    pass


class Canvas:
    def __init__(self):
        self.img = Image.new("RGB", (64, 32))

    def Clear(self):
        self.img.paste((0, 0, 0), (0, 0, 64, 32))

    def SetImage(self, im, x=0, y=0, unsafe=True):
        self.img.paste(im.convert("RGB"), (x, y))

    def SetPixel(self, x, y, r, g, b):
        if 0 <= x < 64 and 0 <= y < 32:
            self.img.putpixel((x, y), (r, g, b))


class RGBMatrix:
    def __init__(self, options=None):
        self.options = options
        self.brightness = 100
        self.c = Canvas()
        self.swaps = 0
        self.shown = None

    def CreateFrameCanvas(self):
        return self.c

    def SwapOnVSync(self, c):
        self.swaps += 1
        self.shown = c.img.copy()
        return c
