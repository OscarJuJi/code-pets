"""Rebuild animation GIFs adding body motion on top of the AI frames.

PixelLab's v3 animation redraws the face, ears and paws convincingly but keeps
the body roughly in place — a "jump" never leaves the ground. This layers the
missing travel over those frames: the AI still supplies the drawing, this
supplies the arc. Free and re-runnable, since it only reads anim/frames/.

    python add_motion.py rottweiler            # every action with frames
    python add_motion.py rottweiler adult      # one stage
"""

import math
import os
import sys

from PIL import Image

sys.stdout.reconfigure(encoding="utf-8")

SPRITES = os.path.dirname(os.path.abspath(__file__))
FRAME_MS = 90
PAD = 1.4  # canvas headroom so the arc never clips


def place(canvas_size, sprite, dx=0, dy=0):
    canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    x = (canvas_size[0] - sprite.size[0]) // 2 + dx
    y = (canvas_size[1] - sprite.size[1]) // 2 + dy
    canvas.paste(sprite, (x, y), sprite)
    return canvas


def motion(frame, action, t):
    """Return (sprite, dx, dy) for phase t (0..1) of the loop."""
    width, height = frame.size

    if action == "jump":
        # one arc across the loop, squashed while still on the ground
        lift = math.sin(math.pi * t)
        squash = 1 - 0.12 * (1 - lift)
        sprite = frame.resize((width, max(1, int(height * squash))), Image.NEAREST)
        return sprite, 0, int(-lift * height * 0.42 + (height - sprite.size[1]))

    if action == "dance":
        # sway side to side with a matching tilt
        angle = 2 * math.pi * t
        sprite = frame.rotate(9 * math.sin(angle), resample=Image.NEAREST, expand=False)
        return sprite, int(math.sin(angle) * width * 0.12), 0

    if action == "sleep":
        # slow breathing: the body swells a little, feet stay planted
        scale = 1 + 0.05 * math.sin(2 * math.pi * t)
        sprite = frame.resize((width, max(1, int(height * scale))), Image.NEAREST)
        return sprite, 0, height - sprite.size[1]

    # "smile" and anything else: a light bob so the pet never looks frozen
    return frame, 0, int(-2 * math.sin(math.pi * t))


def quantize(image):
    """RGBA -> palette image whose last index is transparent."""
    alpha = image.getchannel("A")
    palette = image.convert("RGB").convert("P", palette=Image.ADAPTIVE, colors=255)
    palette.paste(255, alpha.point(lambda a: 255 if a <= 128 else 0))
    return palette


def rebuild(species, folder):
    stage, _, action = folder.partition("_")
    frames_dir = os.path.join(SPRITES, species, "anim", "frames", folder)
    names = sorted(os.listdir(frames_dir), key=lambda n: int(n.split(".")[0]))
    frames = [Image.open(os.path.join(frames_dir, n)).convert("RGBA") for n in names]
    if not frames:
        return False

    width, height = frames[0].size
    canvas_size = (int(width * PAD), int(height * PAD))
    out = []
    for index, frame in enumerate(frames):
        sprite, dx, dy = motion(frame, action, index / len(frames))
        out.append(quantize(place(canvas_size, sprite, dx, dy)))

    out[0].save(
        os.path.join(SPRITES, species, "anim", f"{stage}_{action}.gif"),
        save_all=True, append_images=out[1:], duration=FRAME_MS,
        loop=0, disposal=2, transparency=255, optimize=False,
    )
    return True


species = sys.argv[1] if len(sys.argv) > 1 else "rottweiler"
only_stage = sys.argv[2] if len(sys.argv) > 2 else None
frames_root = os.path.join(SPRITES, species, "anim", "frames")

rebuilt = []
for folder in sorted(os.listdir(frames_root)):
    if only_stage and not folder.startswith(f"{only_stage}_"):
        continue
    if rebuild(species, folder):
        rebuilt.append(folder)

print(f"{len(rebuilt)} GIFs reconstruidos con movimiento: {', '.join(rebuilt)}")
