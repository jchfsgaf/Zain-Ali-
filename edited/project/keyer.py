import numpy as np, cv2

LO, HI = 0.06, 0.15  # green-dominance thresholds: <=LO solid subject, >=HI clean screen

def key(rgb):
    """rgb: float32 HxWx3 in 0..1 (already upscaled). Returns (despilled rgb, alpha)."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    k = g - np.maximum(r, b)
    a = 1.0 - np.clip((k - LO) / (HI - LO), 0, 1)
    a = a.astype(np.float32)
    # clean matte: remove specks in screen, fill holes in subject
    hard = (a > 0.5).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(hard, 8)
    if n > 1:
        keep = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
        big = (lab == keep).astype(np.uint8)
        big = cv2.dilate(big, np.ones((9, 9), np.uint8))
        a *= big
    inv = (a < 0.5).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(inv, 4)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] < 400:
            a[lab == i] = 1.0
    # pull the edge in slightly and soften it
    a = cv2.erode(a, np.ones((3, 3), np.uint8))
    a = cv2.GaussianBlur(a, (0, 0), 1.2)
    # despill: limit green to the stronger of red/blue, keep luminance
    # on soft edges (red chair, hair) use the average of red/blue so no yellow fringe survives
    edge = np.clip((1 - a) * 4, 0, 1)
    lim = np.maximum(r, b) * (1 - edge) + ((r + b) / 2) * edge
    spill = np.clip(g - lim, 0, None)
    out = rgb.copy()
    out[..., 1] = g - spill
    out += (spill * 0.3)[..., None] * np.array([1, 1, 1], np.float32) * 0.5
    return np.clip(out, 0, 1), np.clip(a, 0, 1)

def light_wrap(fg, a, bg, amount=0.35, radius=12):
    """Bleed blurred background light into subject edges for natural integration."""
    bgb = cv2.GaussianBlur(bg, (0, 0), radius)
    inv = cv2.GaussianBlur(1 - a, (0, 0), radius)
    w = np.clip(inv * a * amount * 2, 0, 1)[..., None]
    return fg * (1 - w) + bgb * w
