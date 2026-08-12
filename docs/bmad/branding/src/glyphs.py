# Geist outliner: text -> per-glyph SVG paths + advances at a chosen wght.
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.pens.svgPathPen import SVGPathPen
import copy

_cache = {}
def _inst(path, wght):
    key = (path, wght)
    if key in _cache: return _cache[key]
    f = TTFont(path)
    instantiateVariableFont(f, {"wght": wght}, inplace=True)
    _cache[key] = f
    return f

def upm(path):
    return TTFont(path)["head"].unitsPerEm

def layout(path, text, wght, tracking=0):
    """Return (glyphs, total_advance). glyphs=[{'d':pathdata,'x':xoffset}], y-down flipped so up is +.
    tracking in font units added between glyphs."""
    f = _inst(path, wght)
    cmap = f.getBestCmap()
    gs = f.getGlyphSet()
    hmtx = f["hmtx"]
    glyphs = []
    x = 0
    for ch in text:
        gname = cmap.get(ord(ch))
        if gname is None: 
            x += upm(path)//2 + tracking; continue
        pen = SVGPathPen(gs)
        gs[gname].draw(pen)
        d = pen.getCommands()
        adv = hmtx[gname][0]
        glyphs.append({"d": d, "x": x, "adv": adv, "ch": ch})
        x += adv + tracking
    return glyphs, x

if __name__ == "__main__":
    p = "fonts/GeistSans.ttf"
    print("UPM", upm(p))
    gl, w = layout(p, "K8squad", 600)
    for g in gl: print(g["ch"], "x=", g["x"], "adv=", g["adv"], "dlen=", len(g["d"]))
    print("total width", w)
