"""Compose the edited short: keyed speaker over rendered studio, punch-in zooms,
motion graphics, word-synced captions and a motion-graphic outro."""
import sys, json, subprocess, functools, numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont, ImageFilter
sys.path.insert(0, sys.argv[1])
from keyer import key, light_wrap

SRC, BG, OUT = sys.argv[2], sys.argv[3], sys.argv[4]
W, H, FPS = 1080, 1920, 30
SRC_START = 1.25          # source second where the clean take begins
SPEECH_END = 4.75         # output second where the hook line ends
DUR = 9.4
SRC_LEN = 5.15            # source footage used (covers the zoom transition)
FD = "/usr/share/fonts/opentype/inter/"
TEAL, ORANGE, RED, WHITE, DARK = (46, 230, 214), (255, 159, 67), (255, 71, 87), (255, 255, 255), (12, 18, 32)

@functools.lru_cache(None)
def font(name, size): return ImageFont.truetype(FD + name, size)

def clamp01(x): return min(1.0, max(0.0, x))
def ease_out(x): x = clamp01(x); return 1 - (1 - x) ** 3
def ease_in_out(x): x = clamp01(x); return 3 * x * x - 2 * x * x * x
def back_out(x, s=1.7):
    x = clamp01(x); x -= 1; return x * x * ((s + 1) * x + s) + 1
def prog(t, a, d): return clamp01((t - a) / d)

# ---------------- sprites ----------------
def shadowed(img, blur=10, off=(0, 6), alpha=150, pad=30):
    w, h = img.size
    out = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    sh = Image.new("RGBA", out.size, (0, 0, 0, 0))
    a = img.split()[3].point(lambda v: v * alpha // 255)
    sh.paste(Image.new("RGBA", img.size, (0, 0, 0, 255)), (pad + off[0], pad + off[1]), a)
    out = Image.alpha_composite(out, sh.filter(ImageFilter.GaussianBlur(blur)))
    out.alpha_composite(img, (pad, pad))
    return out

@functools.lru_cache(None)
def text_sprite(text, fname, size, fill, stroke=0, stroke_fill=(0, 0, 0), spacing=0, glow=None):
    f = font(fname, size)
    if spacing:
        widths = [f.getlength(c) + spacing for c in text]; tw = int(sum(widths))
    else:
        tw = int(f.getlength(text))
    asc, desc = f.getmetrics()
    img = Image.new("RGBA", (tw + 2 * stroke + 4, asc + desc + 2 * stroke + 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if spacing:
        x = stroke + 2
        for c, cw in zip(text, widths):
            d.text((x, stroke + 2), c, font=f, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill); x += cw
    else:
        d.text((stroke + 2, stroke + 2), text, font=f, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
    if glow:
        g = Image.new("RGBA", img.size, (*glow, 0)); g.putalpha(img.split()[3])
        pad = 40; big = Image.new("RGBA", (img.width + 2 * pad, img.height + 2 * pad), (0, 0, 0, 0))
        big.paste(g, (pad, pad)); big = big.filter(ImageFilter.GaussianBlur(18))
        big.alpha_composite(img, (pad, pad)); return big
    return shadowed(img)

def pill(w, h, fill, outline=None, r=None):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle([0, 0, w - 1, h - 1], r or h // 2, fill=fill, outline=outline, width=3 if outline else 0)
    return img

@functools.lru_cache(None)
def label_pill(text, size, fg, bg, outline=None, spacing=3):
    t = text_sprite(text, "InterDisplay-Bold.otf", size, fg, spacing=spacing)
    w, h = t.width - 20, int(size * 1.9)
    base = pill(w, h, bg, outline)
    out = Image.new("RGBA", (w + 60, h + 60), (0, 0, 0, 0))
    out.alpha_composite(shadowed(base, pad=30), (0, 0))
    out.alpha_composite(t, ((out.width - t.width) // 2, (out.height - t.height) // 2 - 2))
    return out

@functools.lru_cache(None)
def browser(w, h, seed):
    r = np.random.default_rng(seed)
    accent = [TEAL, ORANGE, (120, 140, 255), (255, 120, 170), (110, 210, 120), (255, 205, 80)][seed % 6]
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w - 1, h - 1], 16, fill=(244, 246, 250, 255))
    d.rounded_rectangle([0, 0, w - 1, 34], 16, fill=(222, 227, 235, 255)); d.rectangle([0, 20, w - 1, 34], fill=(222, 227, 235, 255))
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([14 + i * 20, 11, 26 + i * 20, 23], fill=c)
    d.rounded_rectangle([80, 9, w - 18, 25], 8, fill=(250, 251, 253, 255))
    hy = 48; d.rounded_rectangle([14, hy, w - 14, hy + h * 0.32], 8, fill=(*accent, 255))
    y = hy + h * 0.32 + 14
    while y < h - 40:
        d.rounded_rectangle([14, y, 14 + r.uniform(0.4, 0.85) * (w - 28), y + 9], 4, fill=(205, 211, 222, 255)); y += 20
    d.rounded_rectangle([14, h - 32, 14 + w * 0.32, h - 12], 8, fill=(*DARK, 255))
    return shadowed(img, blur=14, off=(0, 10), alpha=170)

@functools.lru_cache(None)
def badge(kind, r):
    s = r * 2 + 8; img = Image.new("RGBA", (s, s), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    col = RED if kind == "x" else (39, 201, 120)
    d.ellipse([4, 4, s - 4, s - 4], fill=(*col, 255), outline=WHITE, width=max(3, r // 8))
    c, k, lw = s / 2, r * 0.42, max(4, r // 4)
    if kind == "x":
        d.line([c - k, c - k, c + k, c + k], fill=WHITE, width=lw); d.line([c - k, c + k, c + k, c - k], fill=WHITE, width=lw)
    else:
        d.line([c - k, c, c - k * 0.2, c + k * 0.7, c + k, c - k * 0.6], fill=WHITE, width=lw, joint="curve")
    return shadowed(img, blur=8, off=(0, 4), alpha=160, pad=20)

@functools.lru_cache(None)
def five_badge():
    r = 118; s = 2 * r + 80; img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    glow = Image.new("RGBA", (s, s), (0, 0, 0, 0)); ImageDraw.Draw(glow).ellipse([30, 30, s - 30, s - 30], fill=(*RED, 200))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(22)))
    grad = np.zeros((2 * r, 2 * r, 4), np.uint8); yy = np.linspace(0, 1, 2 * r)[:, None]
    for i, (a, b) in enumerate(zip(ORANGE, RED)): grad[..., i] = (a + (b - a) * yy).astype(np.uint8)
    m = Image.new("L", (2 * r, 2 * r), 0); ImageDraw.Draw(m).ellipse([0, 0, 2 * r - 1, 2 * r - 1], fill=255)
    grad[..., 3] = np.asarray(m); img.alpha_composite(Image.fromarray(grad), (40, 40))
    ImageDraw.Draw(img).ellipse([40, 40, 40 + 2 * r - 1, 40 + 2 * r - 1], outline=WHITE, width=6)
    f = font("InterDisplay-Black.otf", 190); tw = f.getlength("5")
    ImageDraw.Draw(img).text((s / 2 - tw / 2, s / 2 - 118), "5", font=f, fill=WHITE)
    return img

def place(ov, spr, cx, cy, scale=1.0, alpha=1.0, rot=0.0):
    if alpha <= 0.01 or scale <= 0.01: return
    s = spr
    if abs(scale - 1) > 1e-3: s = s.resize((max(1, int(s.width * scale)), max(1, int(s.height * scale))), Image.LANCZOS)
    if rot: s = s.rotate(rot, Image.BICUBIC, expand=True)
    if alpha < 1: a = s.split()[3].point(lambda v: int(v * alpha)); s = s.copy(); s.putalpha(a)
    ov.alpha_composite(s, (int(cx - s.width / 2), int(cy - s.height / 2))) if 0 <= int(cx - s.width / 2) and 0 <= int(cy - s.height / 2) and cx + s.width / 2 <= W and cy + s.height / 2 <= H else _paste_clip(ov, s, cx, cy)

def _paste_clip(ov, s, cx, cy):
    x, y = int(cx - s.width / 2), int(cy - s.height / 2)
    l, t = max(0, -x), max(0, -y); r, b = min(s.width, W - x), min(s.height, H - y)
    if r > l and b > t: ov.alpha_composite(s.crop((l, t, r, b)), (x + l, y + t))

# ---------------- captions ----------------
CAPTIONS = [  # (start, end, [ (word, t_show, color) ... ], line breaks by '/')
    (0.08, 2.36, [("I'VE", 0.12, WHITE), ("AUDITED", 0.22, WHITE), ("/", 0, 0), ("100+", 0.38, TEAL), ("WEBSITES", 1.25, (255, 214, 10))]),
    (2.40, 3.38, [("AND", 2.42, WHITE), ("ALL", 2.62, (255, 214, 10)), ("OF", 2.8, WHITE), ("/", 0, 0), ("THEM", 2.9, WHITE), ("HAD", 3.1, WHITE)]),
    (3.38, SPEECH_END, [("5", 3.42, ORANGE), ("COMMON", 3.8, WHITE), ("/", 0, 0), ("MISTAKES", 4.22, RED)]),
]
CAP_Y, CAP_SIZE, CAP_GAP = 1395, 82, 30

def draw_captions(ov, t):
    for s, e, words in CAPTIONS:
        if not (s <= t < e): continue
        out_a = 1 - prog(t, e - 0.12, 0.12)
        lines, cur = [], []
        for w in words:
            if w[0] == "/": lines.append(cur); cur = []
            else: cur.append(w)
        lines.append(cur)
        for li, line in enumerate(lines):
            sprs = [text_sprite(w, "InterDisplay-Black.otf", CAP_SIZE, c if t >= ts else WHITE, stroke=7) for w, ts, c in line]
            widths = [sp.width - 60 for sp in sprs]
            total = sum(widths) + CAP_GAP * (len(sprs) - 1); x = W / 2 - total / 2
            cy = CAP_Y + li * (CAP_SIZE + 18)
            for (w, ts, c), sp, wd in zip(line, sprs, widths):
                p = prog(t, ts, 0.16)
                if t >= ts:
                    sc = 0.6 + 0.4 * back_out(p, 2.4) if c == WHITE else 0.5 + 0.5 * back_out(p, 3.0) + 0.08 * (1 - p)
                    place(ov, sp, x + wd / 2, cy, sc, out_a * clamp01(p * 3))
                x += wd + CAP_GAP

# ---------------- top-zone motion graphics (above the head) ----------------
def card_float(t, ph): return 6 * np.sin(2 * np.pi * (t * 0.45 + ph))

def draw_hook_graphics(ov, t):
    # flanking website cards: scanned + checked in part 1, stamped with an X in part 2
    for i, (cx, ph, t_in, t_ok, t_x) in enumerate([(160, 0.0, 0.12, 1.32, 3.52), (920, 0.4, 0.22, 1.5, 3.64)]):
        if t > SPEECH_END + 0.05: break
        p = back_out(prog(t, t_in, 0.4)); a = clamp01(prog(t, t_in, 0.2)) * (1 - prog(t, SPEECH_END - 0.15, 0.2))
        cy = 300 + card_float(t, ph) + (1 - p) * -120
        place(ov, browser(230, 170, 2 + i), cx, cy, 0.6 + 0.4 * p, a, rot=(4 if i == 0 else -4))
        if t_in + 0.3 < t < 2.3:  # scan bar sweeping the card
            sp = ((t - t_in - 0.3) / 0.9) % 1
            bar = text_sprite("━━━━━━━━", "Inter-Black.otf", 40, TEAL, glow=TEAL)
            place(ov, bar, cx, cy - 70 + sp * 140, 0.75, a * 0.8 * np.sin(np.pi * sp))
        if t_ok <= t < 2.35:
            place(ov, badge("ok", 30), cx + 85, cy - 60, back_out(prog(t, t_ok, 0.25), 3), a)
        if t >= t_x:
            place(ov, badge("x", 34), cx + 85, cy - 60, back_out(prog(t, t_x, 0.25), 3), a)

    # part 1: counter "100+" + "WEBSITES AUDITED"
    if t < 2.5:
        out = ease_in_out(prog(t, 2.28, 0.18)); a = (1 - out) * clamp01(prog(t, 0.05, 0.2))
        dy = -out * 140 + (1 - ease_out(prog(t, 0.0, 0.35))) * -60
        v = int(round(100 * ease_out(prog(t, 0.32, 0.72))))
        txt = f"{v}+" if t >= 1.05 else f"{v}"
        pulse = 1 + 0.12 * (1 - ease_out(prog(t, 1.05, 0.3))) * (t >= 1.05)
        place(ov, text_sprite(txt, "InterDisplay-Black.otf", 200, WHITE, glow=TEAL), W / 2, 225 + dy, pulse, a)
        if t >= 1.18:
            place(ov, label_pill("WEBSITES AUDITED", 44, DARK, (*TEAL, 255)), W / 2, 395 + dy,
                  back_out(prog(t, 1.18, 0.3), 2.5), a * clamp01(prog(t, 1.18, 0.12)))
    # part 2: "FOUND IN ALL OF THEM" + big 5 + "COMMON MISTAKES"
    if 2.4 <= t < SPEECH_END + 0.1:
        a = 1 - prog(t, SPEECH_END - 0.12, 0.18)
        place(ov, label_pill("FOUND IN ALL OF THEM", 36, WHITE, (*DARK, 215), outline=(*TEAL, 255)), W / 2,
              100 + (1 - ease_out(prog(t, 2.45, 0.3))) * -50, 1, a * clamp01(prog(t, 2.45, 0.15)))
        if t >= 3.4:
            p = prog(t, 3.4, 0.2); sc = 0.9 * (1.5 - 0.5 * ease_out(p))
            shake = (1 - prog(t, 3.6, 0.25)) * (t >= 3.6)
            place(ov, five_badge(), W / 2 + shake * 8 * np.sin(t * 90), 268, sc, a * clamp01(p * 2.5))
            ring = prog(t, 3.58, 0.45)
            if 0 < ring < 1:
                rimg = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
                ImageDraw.Draw(rimg).ellipse([6, 6, 294, 294], outline=(*ORANGE, int(255 * (1 - ring))), width=8)
                place(ov, rimg, W / 2, 268, 0.8 + 0.45 * ease_out(ring), a)
        if t >= 3.78:
            place(ov, text_sprite("COMMON MISTAKES", "InterDisplay-Black.otf", 64, WHITE, spacing=2), W / 2,
                  425 - (1 - ease_out(prog(t, 3.78, 0.3))) * 30, 1, a * clamp01(prog(t, 3.78, 0.15)))

# ---------------- outro (motion-graphic B-roll) ----------------
def outro_bg():
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    base = np.zeros((H, W, 3), np.float32)
    top, bot = np.array([10, 16, 30]) / 255, np.array([18, 30, 52]) / 255
    base[:] = top + (bot - top) * (yy / H)[..., None]
    for cx, cy, r, c in [(200, 300, 520, TEAL), (900, 1600, 600, (120, 90, 255)), (950, 500, 380, RED)]:
        g = np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * r * r))[..., None] * 0.22
        base += g * np.array(c) / 255
    grid = ((xx % 90 < 2) | (yy % 90 < 2)).astype(np.float32)[..., None] * 0.035
    return np.clip(base + grid, 0, 1)

GRID = [(300 + 480 * (i % 2), 520 + 330 * (i // 2)) for i in range(6)]

def draw_outro(ov, t):
    lt = t - SPEECH_END
    dim = clamp01(prog(lt, 2.25, 0.3))
    for i, (cx, cy) in enumerate(GRID):
        ti = 0.25 + i * 0.08; p = back_out(prog(lt, ti, 0.45))
        a = clamp01(prog(lt, ti, 0.15)) * (1 - 0.88 * dim)
        place(ov, browser(400, 280, i), cx + (1 - p) * (300 if i % 2 else -300), cy + card_float(t, i * 0.17), 0.85 + 0.15 * p, a)
        tx = 1.72 + i * 0.09
        if lt >= tx:
            place(ov, badge("x", 44), cx + 150, cy - 95, back_out(prog(lt, tx, 0.25), 3), a)
    sp = prog(lt, 0.9, 0.8)
    if 0 < sp < 1:
        bar = Image.new("RGBA", (W, 60), (0, 0, 0, 0))
        ImageDraw.Draw(bar).rectangle([60, 26, W - 60, 34], fill=(*TEAL, 255))
        bar = bar.filter(ImageFilter.GaussianBlur(6)); ImageDraw.Draw(bar).rectangle([60, 28, W - 60, 31], fill=(220, 255, 252, 255))
        place(ov, bar, W / 2, 330 + sp * 1050, 1, np.sin(np.pi * sp) ** 0.5)
    if lt >= 2.3:
        p = prog(lt, 2.3, 0.22)
        for k, (txt, c, y, sz) in enumerate([("5 COMMON", WHITE, 760, 132), ("WEBSITE", WHITE, 900, 132), ("MISTAKES", RED, 1040, 150)]):
            pk = prog(lt, 2.3 + k * 0.07, 0.22)
            place(ov, text_sprite(txt, "InterDisplay-Black.otf", sz, c, glow=(c if c != WHITE else None)), W / 2, y,
                  1.8 - 0.8 * ease_out(pk), clamp01(pk * 3))
        if lt >= 2.85:
            place(ov, text_sprite("Are you making them too?", "InterDisplay-Medium.otf", 58, (220, 228, 240)), W / 2,
                  1195 + (1 - ease_out(prog(lt, 2.85, 0.35))) * 30, 1, clamp01(prog(lt, 2.85, 0.25)))
        if lt >= 3.45:
            place(ov, label_pill("FOLLOW FOR MORE  →", 46, DARK, (*TEAL, 255), spacing=2), W / 2, 1360,
                  back_out(prog(lt, 3.45, 0.35), 2.5), clamp01(prog(lt, 3.45, 0.12)))

# ---------------- camera ----------------
def zoom_at(t):
    if t < 2.38: return 1.0 + 0.035 * ease_in_out(t / 2.38)
    if t < SPEECH_END: return 1.035 + 0.095 * ease_out(prog(t, 2.38, 0.14)) + 0.03 * prog(t, 2.52, SPEECH_END - 2.52)
    return 1.16 + 0.5 * ease_in_out(prog(t, SPEECH_END, 0.32))

def warp(img, z, cx, cy, interp=cv2.INTER_LINEAR):
    M = np.float32([[z, 0, cx * (1 - z)], [0, z, cy * (1 - z)]])
    return cv2.warpAffine(img, M, (W, H), flags=interp, borderMode=cv2.BORDER_REFLECT)

def face_box(fg, a):
    ycc = cv2.cvtColor((fg * 255).astype(np.uint8), cv2.COLOR_RGB2YCrCb)
    m = ((ycc[..., 1] > 138) & (ycc[..., 1] < 175) & (ycc[..., 2] > 85) & (ycc[..., 2] < 128) & (a > 0.5)).astype(np.uint8)
    m[:420] = 0; m[1250:] = 0
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    n, lab, st, cen = cv2.connectedComponentsWithStats(m, 8)
    if n < 2: return None
    # face = largest skin blob whose top lies in the upper part of the subject
    cand = [i for i in range(1, n) if st[i, cv2.CC_STAT_TOP] < 800 and cen[i][1] < 1050 and st[i, cv2.CC_STAT_AREA] > 4000]
    if not cand: return None
    i = max(cand, key=lambda i: st[i, cv2.CC_STAT_AREA])
    x, y, w, h = st[i, :4]
    return (x, y - int(0.25 * h), x + w, y + h)  # extend up to cover hair/forehead

def main():
    bg_img = cv2.cvtColor(cv2.imread(BG), cv2.COLOR_BGR2RGB)
    bg_img = cv2.resize(bg_img, (W, H), interpolation=cv2.INTER_AREA).astype(np.float32) / 255
    obg = outro_bg()
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", str(SRC_START), "-i", SRC, "-t", str(SRC_LEN),
                            "-vf", f"fps={FPS},scale={W}:{H}:flags=lanczos", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                           stdout=subprocess.PIPE)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                            "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "17",
                            "-pix_fmt", "yuv420p", OUT], stdin=subprocess.PIPE)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    vign = (1 - 0.32 * (((xx - W / 2) / (W * 0.75)) ** 2 + ((yy - H * 0.45) / (H * 0.7)) ** 2)).clip(0.55, 1)[..., None]
    rng = np.random.default_rng(1)
    nframes = int(DUR * FPS); last = None; cx, cy = W / 2, 800.0
    report = {"face_overlap_px": 0, "frames_checked": 0, "no_face": 0}
    for fi in range(nframes):
        t = fi / FPS
        raw = dec.stdout.read(W * H * 3) if t < SRC_LEN else b""
        if len(raw) == W * H * 3: last = np.frombuffer(raw, np.uint8).reshape(H, W, 3)
        comp = None
        if t < SPEECH_END + 0.4:
            src = last.astype(np.float32) / 255
            fg, a = key(src)
            # gentle grade on the speaker: a touch of contrast & warmth to sit in the warm room
            fg = np.clip((fg - 0.5) * 1.06 + 0.5, 0, 1) * np.array([1.02, 1.0, 0.97], np.float32)
            sharp = cv2.GaussianBlur(fg, (0, 0), 1.5); fg = np.clip(fg * 1.35 - sharp * 0.35, 0, 1)
            if fi == 0:
                fb = face_box(fg, a)
                if fb: cx, cy = (fb[0] + fb[2]) / 2, (fb[1] + fb[3]) / 2
            z = zoom_at(t)
            fgw = warp(fg, z, cx, cy, cv2.INTER_CUBIC); aw = warp(a, z, cx, cy)
            bgw = warp(bg_img, 1 + (z - 1) * 0.55, cx, cy)
            fgw = light_wrap(fgw, aw, bgw, amount=0.3)
            comp = fgw * aw[..., None] + bgw * (1 - aw[..., None])
            if t > SPEECH_END:  # zoom-blur transition into the outro
                p = prog(t, SPEECH_END, 0.32)
                blur = cv2.GaussianBlur(comp, (0, 0), 1 + 25 * p)
                comp = comp * (1 - p) + blur * p
                comp = comp * (1 - ease_in_out(prog(t, SPEECH_END + 0.12, 0.25))) + obg * ease_in_out(prog(t, SPEECH_END + 0.12, 0.25))
            fbox = face_box(fgw, aw) if t < SPEECH_END else None
        else:
            comp = obg.copy(); fbox = None
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        if t < SPEECH_END + 0.1:
            draw_hook_graphics(ov, t); draw_captions(ov, t)
        if t >= SPEECH_END:
            draw_outro(ov, t)
        ova = np.asarray(ov).astype(np.float32) / 255
        if t < SPEECH_END:
            report["frames_checked"] += 1
            if fbox:
                x0, y0, x1, y1 = fbox
                ovl = int((ova[max(0, y0):y1, max(0, x0):x1, 3] > 0.05).sum()); report["face_overlap_px"] += ovl
                if ovl: report.setdefault("hits", []).append((round(t, 2), [int(v) for v in fbox], ovl))
            else:
                report["no_face"] += 1
        comp = comp * (1 - ova[..., 3:]) + ova[..., :3] * ova[..., 3:]
        comp = comp * vign + rng.normal(0, 0.012, (H // 2, W // 2, 1)).repeat(2, 0).repeat(2, 1)
        fade = 1 - prog(t, DUR - 0.45, 0.45)
        frame = (np.clip(comp * fade, 0, 1) * 255).astype(np.uint8)
        enc.stdin.write(frame.tobytes())
        if fi % 30 == 0: print(f"frame {fi}/{nframes}", flush=True)
        if fi in (12, 40, 75, 105, 125, 150, 175, 215, 240, 262):
            cv2.imwrite(OUT.replace(".mp4", f"_f{fi:03d}.jpg"), cv2.cvtColor(frame, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 85])
    enc.stdin.close(); enc.wait(); dec.kill()
    print(json.dumps(report))

main()
