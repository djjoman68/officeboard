class Color:
    def __init__(self, r=0, g=0, b=0): self.red, self.green, self.blue = r, g, b
class Font:
    def LoadFont(self, path): self.path = path
    def CharacterWidth(self, c): return 5
def DrawText(canvas, font, x, y, color, text):
    # crude stand-in: mark one pixel per character so we can see something drew
    for i, _ in enumerate(text):
        canvas.SetPixel(x + i * 5, max(0, y - 1), color.red, color.green, color.blue)
    return len(text) * 5
def DrawLine(canvas, x0, y0, x1, y1, color):
    for y in range(min(y0, y1), max(y0, y1) + 1):
        canvas.SetPixel(x0, y, color.red, color.green, color.blue)
