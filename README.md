# Pet sprites

One folder per species. A species appears in the dashboard picker as soon as it
has at least one stage sprite; stages fall back to ASCII art individually, so a
half-finished set is fine.

```
sprites/
  rottweiler/          # "Rottweiler" — chibi, the default
    puppy.png hatchling.png juvenile.png adult.png veteran.png legend.png
    anim/
      <stage>_jump.gif  <stage>_smile.gif  <stage>_dance.gif  <stage>_sleep.gif
      frames/<stage>_<action>/0.png…       # raw AI frames, kept for re-timing
    object_ids.json    # PixelLab object per stage — needed to add animations
  dog/                 # "Perro robot"
  blob/                # "Blob digital"
```

| Stage (UI) | File slug   | XP  |
|------------|-------------|-----|
| cachorro   | `puppy`     | 0   |
| cría       | `hatchling` | 50  |
| juvenil    | `juvenile`  | 150 |
| adulto     | `adult`     | 350 |
| veterano   | `veteran`   | 700 |
| leyenda    | `legend`    | 1200|

## Stage sprites

Transparent background, square, 64×64 or smaller — they render at 160×160 with
`image-rendering: pixelated`, so a small source stays crisp while an upscaled
one just looks blurry.

Generated with PixelLab (`create_map_object`): 64×64, `view="side"`,
`outline="single color outline"`, `shading="basic shading"`,
`detail="low detail"`. The rottweiler prompts pin the look with *"super
deformed chibi style, huge oversized round head, enormous sparkling eyes, tiny
body, kawaii mascot, retro 16-bit pixel art"* plus the coat description — keep
those phrases when adding a stage or the new sprite drifts off-model.

## Interaction animations

`anim/<stage>_<action>.gif` plays when the pet is interacted with. The frontend
splits actions by intent: `jump`, `smile` and `dance` answer interactions;
`sleep` plays on its own when the pet is bored, sad or hungry. Any other file
name is treated as generic (that is how the older `blob`/`dog` sets, whose
actions are `jump/spin/wag/happy`, keep working).

Two ways to make them, both ending in a transparent looping GIF at 90 ms/frame:

- **`gen_anims.py` — real animation (costs credits).** Queues
  `animate_object(mode="v3", frame_count=8)` per action, waits, then downloads
  the object's ZIP from `api.pixellab.ai/mcp/objects/<id>/download` — the CDN
  frame URLs 403 even with the token, the ZIP is the only path that works. It
  needs `object_ids.json`, and PixelLab **deletes objects after 8 h**, so an
  object can only gain animations the same day it was created. Raw frames are
  kept under `anim/frames/` so GIFs can be re-timed for free afterwards.
- **`add_motion.py` — the finishing pass, free.** Run it after `gen_anims.py`.
  v3 redraws the face, ears and paws well but barely moves the body: its
  "jump" never leaves the ground. This rebuilds each GIF from `anim/frames/`
  with the missing travel layered on (arc plus squash for `jump`, sway and
  tilt for `dance`, breathing for `sleep`, a light bob otherwise). The AI still
  supplies the drawing; this supplies the motion. Re-runnable at no cost —
  edit the curves in `motion()` and run it again.
- **`gen_gifs.py` — synthesized, free.** Transforms the stage sprite itself
  (jump, spin, wag, happy). No new art, so the dog never bends a leg or smiles,
  but it costs nothing and always matches the sprite.
  `python gen_gifs.py rottweiler puppy hatchling` limits it to given stages.

## Adding a species

1. Create `sprites/<key>/` and generate the stage PNGs (save the object ids).
2. Add `"<key>": "<label>"` to `SPECIES_LABELS` in `app.py`.
3. Animate: `gen_anims.py` the same day, or `gen_gifs.py` for the free version.
