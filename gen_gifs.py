"""Build interaction GIFs from the stage sprites themselves.

Animating the actual sprite (instead of generating a second character) keeps
the animation and the still frame identical, costs no PixelLab credits, and
works for every species and stage.

Output: <sprites>/<species>/anim/<stage>_<action>.gif
"""

import math
import os
import sys

from PIL import Image

sys.stdout.reconfigure(encoding="utf-8")

SPRITES = r"E:\Workspace\codepet\web\static\sprites"
STAGES = ["puppy", "hatchling", "juvenile", "adult", "veteran", "legend"]
FRAMES = 8
FRAME_MS = 90
PAD = 1.4  # canvas headroom so movement and rotation never clip


def transform(sprite, action, t):
    """Return the sprite transformed for phase t (0..1) of one loop."""
    width, height = sprite.size
    angle = 2 * math.pi * t

    if action == "jump":
        # up-and-over arc with a squash on landing
        lift = math.sin(math.pi * t)
        squash = 1 - 0.18 * max(0.0, math.cos(math.pi * t * 2)) if t > 0.75 else 1
        frame = sprite.resize((width, max(1, int(height * squash))), Image.NEAREST)
        return frame, 0, int(-lift * height * 0.35 + (height - frame.size[1]))

    if action == "spin":
        # horizontal scale through zero reads as a turn in pixel art
        scale = math.cos(angle)
        new_width = max(1, int(abs(scale) * width))
        frame = sprite.resize((new_width, height), Image.NEAREST)
        if scale < 0:
            frame = frame.transpose(Image.FLIP_LEFT_RIGHT)
        return frame, (width - new_width) // 2, 0

    if action == "wag":
        frame = sprite.rotate(14 * math.sin(angle), resample=Image.NEAREST, expand=False)
        return frame, int(2 * math.sin(angle)), 0

    # "happy": bouncing scale pulse
    scale = 1 + 0.14 * math.sin(angle)
    size = (max(1, int(width * scale)), max(1, int(height * scale)))
    frame = sprite.resize(size, Image.NEAREST)
    return frame, (width - size[0]) // 2, (height - size[1])


def quantize(image):
    """RGBA -> palette image whose last index is transparent."""
    alpha = image.getchannel("A")
    palette_image = image.convert("RGB").convert("P", palette=Image.ADAPTIVE, colors=255)
    palette_image.paste(255, alpha.point(lambda a: 255 if a <= 128 else 0))
    return palette_image


def build(sprite_path, out_path, action):
    sprite = Image.open(sprite_path).convert("RGBA")
    width, height = sprite.size
    canvas_size = (int(width * PAD), int(height * PAD))
    offset = ((canvas_size[0] - width) // 2, (canvas_size[1] - height) // 2)

    frames = []
    for index in range(FRAMES):
        frame_sprite, dx, dy = transform(sprite, action, index / FRAMES)
        canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
        canvas.paste(frame_sprite, (offset[0] + dx, offset[1] + dy), frame_sprite)
        frames.append(quantize(canvas))

    frames[0].save(
        out_path, save_all=True, append_images=frames[1:],
        duration=FRAME_MS, loop=0, disposal=2, transparency=255, optimize=False,
    )
    return os.path.getsize(out_path)


# python gen_gifs.py                          -> every species, every stage
# python gen_gifs.py rottweiler puppy hatchling -> just those stages
argv = sys.argv[1:]
species_list = [argv[0]] if argv else ["blob", "dog", "rottweiler"]
stage_list = argv[1:] or STAGES

total = 0
for species in species_list:
    anim_dir = os.path.join(SPRITES, species, "anim")
    os.makedirs(anim_dir, exist_ok=True)
    for stage in stage_list:
        sprite_path = os.path.join(SPRITES, species, f"{stage}.png")
        if not os.path.exists(sprite_path):
            continue
        for action in ("jump", "spin", "wag", "happy"):
            build(sprite_path, os.path.join(anim_dir, f"{stage}_{action}.gif"), action)
            total += 1
    print(f"{species}: listo")

print(f"\n{total} GIFs generados")
