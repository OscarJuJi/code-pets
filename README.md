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


## Interaction animations

`anim/<stage>_<action>.gif` plays when the pet is interacted with. The frontend
splits actions by intent: `jump`, `smile` and `dance` answer interactions;
`sleep` plays on its own when the pet is bored, sad or hungry. Any other file
name is treated as generic (that is how the older `dog` sets, whose
actions are `jump/spin/wag/happy`, keep working).
