"""Original music bed + synthesized SFX (no third-party samples) and the final mix."""
import sys, json, numpy as np, soundfile as sf
from scipy import signal

SR = 48000
rng = np.random.default_rng(3)
T = json.load(open(sys.argv[1]))  # timeline: {"dur":..., "speech_end":..., "sfx":[[name,t,gain_db],...]}
DUR = T["dur"]
N = int(DUR * SR)

def t_(d): return np.arange(int(d * SR)) / SR
def env(n, a, d):  # attack/exp-decay envelope
    x = np.arange(n) / SR
    return np.minimum(x / max(a, 1e-4), 1) * np.exp(-x / d)
def bp(x, lo, hi, order=2):
    sos = signal.butter(order, [lo, hi], "bandpass", fs=SR, output="sos"); return signal.sosfilt(sos, x)
def lp(x, f, order=2):
    sos = signal.butter(order, f, "lowpass", fs=SR, output="sos"); return signal.sosfilt(sos, x)
def hp(x, f, order=2):
    sos = signal.butter(order, f, "highpass", fs=SR, output="sos"); return signal.sosfilt(sos, x)
def sweep_filter(x, f0, f1, q=1.5, blocks=64):
    out = np.zeros_like(x); L = len(x); bs = L // blocks + 1
    zi = None
    for i in range(blocks):
        f = f0 * (f1 / f0) ** (i / (blocks - 1))
        sos = signal.butter(2, [f / (1 + 1 / q), min(f * (1 + 1 / q), SR / 2 - 100)], "bandpass", fs=SR, output="sos")
        if zi is None: zi = np.zeros((sos.shape[0], 2))
        seg = x[i * bs:(i + 1) * bs]
        out[i * bs:i * bs + len(seg)], zi = signal.sosfilt(sos, seg, zi=zi)
    return out
def norm(x, peak=0.9): return x / (np.max(np.abs(x)) + 1e-9) * peak

# ---------------- SFX ----------------
def whoosh(d=0.55, up=False):
    n = int(d * SR); x = rng.standard_normal(n)
    x = sweep_filter(x, 300, 5000) if up else sweep_filter(x, 4500, 250)
    e = np.sin(np.linspace(0, np.pi, n)) ** 2
    return norm(x * e, 0.8)
def pop(f0=1100):
    tt = t_(0.09); f = f0 * np.exp(-tt * 18)
    return norm(np.sin(2 * np.pi * np.cumsum(f) / SR) * env(len(tt), 0.002, 0.025), 0.8)
def tick():
    tt = t_(0.025); return norm(np.sin(2 * np.pi * 2600 * tt) * env(len(tt), 0.0005, 0.005), 0.5)
def ding():
    tt = t_(1.4); x = sum(a * np.sin(2 * np.pi * 1318.5 * r * tt) * np.exp(-tt * k)
                          for r, a, k in [(1, 1, 3), (2.0, 0.4, 5), (2.76, 0.25, 7), (5.4, 0.1, 10)])
    return norm(x * np.minimum(tt / 0.003, 1), 0.7)
def impact():
    tt = t_(1.2); f = 40 + 90 * np.exp(-tt * 12)
    boom = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 3.2)
    crack = hp(rng.standard_normal(len(tt)), 1500) * np.exp(-tt * 30) * 0.5
    return norm(np.tanh(1.6 * (boom + crack)), 0.95)
def riser(d=1.0):
    n = int(d * SR); tt = np.arange(n) / SR
    x = sweep_filter(rng.standard_normal(n), 400, 7000, q=3) * (tt / d) ** 2
    tone = np.sin(2 * np.pi * np.cumsum(220 * 4 ** (tt / d)) / SR) * (tt / d) ** 2 * 0.25
    return norm(x + tone, 0.6)
def shimmer():
    out = np.zeros(int(1.2 * SR))
    for i, fr in enumerate([1760, 2217, 2637, 3520, 2637, 3322]):
        s = int(i * 0.06 * SR); tt = t_(0.6)
        out[s:s + len(tt)] += np.sin(2 * np.pi * fr * tt) * np.exp(-tt * 7) * 0.4
    return norm(out, 0.5)
def scan(d=0.9):
    tt = t_(d); x = np.sin(2 * np.pi * (600 + 900 * tt / d) * tt) * 0.3 + sweep_filter(rng.standard_normal(len(tt)), 1500, 6000, q=4) * 0.6
    return norm(x * np.sin(np.pi * tt / d) ** 0.5, 0.45)
SFX = {"whoosh": whoosh, "whoosh_up": lambda: whoosh(0.5, True), "pop": pop, "pop_hi": lambda: pop(1500),
       "tick": tick, "ding": ding, "impact": impact, "riser": riser, "shimmer": shimmer, "scan": scan}

# ---------------- music (original, 110 bpm, Am-F-C-G) ----------------
BPM = 110; beat = 60 / BPM
def note(m): return 440 * 2 ** ((m - 69) / 12)
chords = [[57, 60, 64], [53, 57, 60], [48, 55, 60, 64], [55, 59, 62]]
roots = [45, 41, 48, 43]
music = np.zeros(N + SR); drums = np.zeros(N + SR)
def add(buf, x, t, g=1.0):
    s = int(t * SR); e = min(len(buf), s + len(x));
    if s < len(buf): buf[s:e] += x[:e - s] * g
bar = 4 * beat; nbars = int(DUR / bar) + 2
for b in range(nbars):
    ch = chords[b % 4]; t0 = b * bar
    tt = t_(bar + 0.3)
    pad = sum(np.sin(2 * np.pi * note(m) * d * tt + rng.uniform(0, 6)) for m in ch for d in (0.997, 1.003))
    pad = lp(pad + 0.3 * np.sign(np.sin(2 * np.pi * note(ch[0]) * tt)), 1400) * np.minimum(tt / 0.25, 1) * np.minimum((bar + 0.3 - tt) / 0.3, 1)
    add(music, pad * 0.05, t0)
    sub = np.sin(2 * np.pi * note(roots[b % 4]) * tt) * np.minimum(tt / 0.02, 1) * np.minimum((bar - tt).clip(0) / 0.05, 1)
    add(music, sub * 0.22, t0)
    arp = ch + [ch[1] + 12, ch[0] + 12, ch[2], ch[1] + 12, ch[2] + 12]
    for k in range(8):
        tp = t_(0.5); f = note(arp[k % len(arp)] + 12)
        pl = (np.sin(2 * np.pi * f * tp) + 0.35 * np.sin(4 * np.pi * f * tp) + 0.15 * np.sin(6 * np.pi * f * tp)) * env(len(tp), 0.003, 0.12)
        add(music, pl * 0.09, t0 + k * beat / 2)
    for k in range(4):
        tk = t_(0.35); fk = 45 + 110 * np.exp(-tk * 30)
        add(drums, np.sin(2 * np.pi * np.cumsum(fk) / SR) * np.exp(-tk * 9) * 0.55, t0 + k * beat)
        if k in (1, 3):
            add(drums, bp(rng.standard_normal(int(0.2 * SR)), 900, 5000) * env(int(0.2 * SR), 0.001, 0.05) * 0.35, t0 + k * beat)
        for h in (0, 0.5):
            add(drums, hp(rng.standard_normal(int(0.05 * SR)), 7000) * env(int(0.05 * SR), 0.0005, 0.012) * 0.18, t0 + (k + h) * beat)
music = music[:N]; drums = drums[:N]

# drums only after the hook; light music bed under the voice, full in the outro
se = T["speech_end"]
tt = np.arange(N) / SR
mus_gain = np.where(tt < se, 10 ** (-23 / 20), 10 ** (-9 / 20))
ramp = np.clip((tt - (se - 0.25)) / 0.35, 0, 1)
mus_gain = 10 ** ((-23 + 14 * ramp) / 20)
fade = np.clip((DUR - tt) / 0.8, 0, 1)
bed = (music + drums * ramp) * mus_gain * fade

voice, vsr = sf.read(sys.argv[2]); assert vsr == SR
if voice.ndim > 1: voice = voice.mean(1)
vo = np.zeros(N); vo[:min(N, len(voice))] = voice[:N]

fx = np.zeros(N + 2 * SR)
for name, t, g in T["sfx"]:
    add(fx, SFX[name](), t, 10 ** (g / 20))
fx = fx[:N]

mix = vo + bed + fx * 0.5
mix = mix / max(1.0, np.max(np.abs(mix)) / 0.97)
sf.write(sys.argv[3], np.stack([mix, mix], 1).astype(np.float32), SR)
print("ok", DUR)
