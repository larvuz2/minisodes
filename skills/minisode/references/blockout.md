# Block out the locations

Before any image of a place, build it in gray like a Blender blockout: walls, furniture, actor marks, cameras.
It fixes the geography (where the door is, who sits where, which way the light comes from) so every plate,
keyframe and shot agrees, and it lets you check each camera of the shot list before paying for a frame.

```bash
node scripts/blockout.mjs blockout/glasshouse.json -o blockout/glasshouse/
```

Outputs, per camera: `<cam>.png` (clay with colored mannequins on their marks), `<cam>_empty.png` (no people:
the base of the location plates), `<cam>_labels.png` (names drawn on: read it to check the framing);
`<cam>_move.mp4` for a camera with a `move`; `plan.png` (top view with furniture, marks, camera frustums and a
1 m grid); `<name>.glb` (opens in Blender, to refine by hand if ever needed); `manifest.json`.

## The layout (`templates/layout.json`)

Meters, Y up, origin at the room center, north is -z. Furniture and actors face +z locally; `rot` turns them
around Y in degrees (90 faces +x, 180 faces -z, -90 faces -x).

- `room`: `w`, `d`, `h`, `walls` (north/south/east/west), `glass: true` for glass walls with mullions,
  `ceiling: true` for a closed room.
- `objects`: `{id, type, pos, rot, size, label}`. Types: box, cylinder, sphere, plane (rugs, dance floors),
  table, round_table (`cloth: true` for a tablecloth to the floor), chair, sofa, bed, counter, shelf, door,
  window (`sill`), lamp, plant, screen (`elev`), column, stairs (`steps`), flowers (`elev`), and
  `string_lights` (`from`, `to`, `sag`, `bulbs`). `label: false` hides a label in the plan.
- `actors`: `{id, name, pos, rot, pose: "stand" | "sit", height, color}`. Each actor has a distinct color; the
  keyframe prompts name them ("the violet mannequin is Nora").
- `cameras`: `{id, pos, look, lens, roll}`; `move: {pos, look, lens, seconds, ease, actors}` for a camera move.
  The lens is in full-frame millimeters on the long edge of the frame: 24-28 wide, 35 normal-wide, 50 normal,
  85 close-up portrait, 100+ compressed. Name cameras after the shots they serve (`cu_nora`, `ots_nora`).
- `sun` (direction, intensity), `practicals` (point lights), `background`.

## Placing cameras

- Heights: eye level is the eye height of the subject (1.2 m seated, 1.6 m standing); "slightly low" is 0.2-0.4 m
  under it; "low" is table height.
- Distance for a close-up on 85 mm: about 0.9-1.2 m from the face; a medium close-up on 50 mm about 1.2-1.5 m; a
  two-shot on 35 mm about 2-2.5 m.
- Over-the-shoulder: behind and to one side of the near actor, at their shoulder height, looking at the far
  actor's eyes. Keep every camera of a conversation on one side of the line between the two actors (the
  180-degree rule); the plan shows the frustums, so check it there.
- Vertical framing: the frame is tall and narrow. Close singles and two-shots stacked in depth work; wide
  side-by-side two-shots do not.

## Using the renders

- `<cam>_empty.png` → the location plates (`bible.md`), one per main direction.
- `<cam>.png` with mannequins → the layout image of a keyframe.
- `<cam>_labels.png` and `plan.png` → your check: does the camera see what the shot needs? Fix the layout or the
  camera, not the prompt.
- `<cam>_move.mp4` → only as a last-resort video reference (`shoot-and-review.md`), when a camera move does not
  happen from words alone. It carries the move, not the look; the prompt says so.
