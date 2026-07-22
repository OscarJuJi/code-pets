"""Give the chibi rottweiler natural, frame-by-frame animations.

For each stage: queue its actions with animate_object (v3, 8 frames), wait for
the jobs, then pull the object's ZIP once — it carries every frame of every
animation. The CDN frame URLs 403 even with the token, so the ZIP endpoint is
the only working download path.

Frames are kept under anim/frames/ because PixelLab deletes objects after 8h;
with the PNGs on disk the GIFs can be re-timed later for free.
"""

import io
import json
import os
import re
import sys
import time
import urllib.request
import zipfile

from PIL import Image

import pixellab

sys.stdout.reconfigure(encoding="utf-8")

SPRITES = r"E:\Workspace\codepet\web\static\sprites"
SPECIES = "rottweiler"
FRAME_MS = 90

# action -> description handed to the model
ACTIONS = {
    "jump": "jumping excitedly with bent legs and bouncing floppy ears",
    "smile": "smiling happily with tongue out and tail wagging",
    "dance": "dancing on hind legs with rhythmic side steps",
    "sleep": "lying down curled up sleeping peacefully",
}
# stage -> actions still missing (adult already has jump from the pipeline test)
PLAN = {
    "adult": ["smile", "dance", "sleep"],
    "juvenile": ["jump", "smile", "dance", "sleep"],
    "veteran": ["jump", "smile", "dance", "sleep"],
    "legend": ["jump", "smile", "dance", "sleep"],
}


def auth_headers():
    with open(os.path.expanduser("~/.claude.json"), encoding="utf-8") as f:
        srv = json.load(f)["projects"]["E:/Workspace"]["mcpServers"]["pixellab"]
    return dict(srv.get("headers") or {})


def folder_slug(description):
    """How PixelLab names the animation folder inside the ZIP."""
    return re.sub(r"[^a-z0-9]+", "_", description.lower())[:50].rstrip("_")


def queue_action(object_id, action, attempts=5):
    for _ in range(attempts):
        text = pixellab.text_of(pixellab.call("animate_object", {
            "object_id": object_id,
            "mode": "v3",
            "animation_description": ACTIONS[action],
            "frame_count": 8,
            "display_name": action,
        }))
        if "group:" in text:
            return True
        if "rate limit" in text.lower():
            time.sleep(30)
            continue
        print(f"    FALLO {action}: {text[:140]}")
        return False
    return False


def wait_for_jobs(object_id, minutes=25):
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        text = pixellab.text_of(pixellab.call(
            "get_object", {"object_id": object_id, "include_preview": False}))
        if "pending jobs" not in text.lower():
            return True
        progress = [l.strip() for l in text.splitlines() if "%" in l]
        print(f"    {progress[0][:70] if progress else 'esperando'}")
        time.sleep(30)
    return False


def build_gifs(stage, object_id, actions):
    url = f"https://api.pixellab.ai/mcp/objects/{object_id}/download"
    req = urllib.request.Request(url, headers=auth_headers())
    with urllib.request.urlopen(req, timeout=180) as response:
        archive = zipfile.ZipFile(io.BytesIO(response.read()))

    anim_dir = os.path.join(SPRITES, SPECIES, "anim")
    os.makedirs(anim_dir, exist_ok=True)
    built = []
    for action in actions:
        slug = folder_slug(ACTIONS[action])
        names = sorted(n for n in archive.namelist()
                       if n.startswith(f"animations/{slug}/") and n.endswith(".png"))
        if not names:
            print(f"    sin cuadros en el zip para {action}")
            continue

        raw_dir = os.path.join(anim_dir, "frames", f"{stage}_{action}")
        os.makedirs(raw_dir, exist_ok=True)
        frames = []
        for index, name in enumerate(names):
            data = archive.read(name)
            with open(os.path.join(raw_dir, f"{index}.png"), "wb") as f:
                f.write(data)
            frames.append(Image.open(io.BytesIO(data)).convert("RGBA"))

        quantized = []
        for frame in frames:
            alpha = frame.getchannel("A")
            palette_image = frame.convert("RGB").convert("P", palette=Image.ADAPTIVE, colors=255)
            palette_image.paste(255, alpha.point(lambda a: 255 if a <= 128 else 0))
            quantized.append(palette_image)
        quantized[0].save(
            os.path.join(anim_dir, f"{stage}_{action}.gif"),
            save_all=True, append_images=quantized[1:], duration=FRAME_MS,
            loop=0, disposal=2, transparency=255, optimize=False,
        )
        built.append(f"{action}({len(frames)})")
    print(f"  {stage}: {', '.join(built) if built else 'nada'}")
    return len(built)


ids = json.load(open(os.path.join(SPRITES, SPECIES, "object_ids.json"), encoding="utf-8"))
total = 0
for stage, actions in PLAN.items():
    object_id = ids.get(stage)
    if not object_id:
        print(f"{stage}: sin object_id, se salta")
        continue
    print(f"{stage}: encolando {len(actions)} animaciones")
    queued = [a for a in actions if queue_action(object_id, a)]
    if not queued:
        continue
    wait_for_jobs(object_id)
    # the ZIP holds every animation this object has, including earlier ones
    all_actions = list(dict.fromkeys(queued + (["jump"] if stage == "adult" else [])))
    total += build_gifs(stage, object_id, all_actions)

print(f"\nGIFs de IA generados: {total}")
