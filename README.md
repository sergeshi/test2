# Level Archaeologist — prototype 0.1

A small Windows desktop prototype for studying game-level geometry and exporting simplified blockouts to Blender.

## What this prototype does

- Imports geometry from common interchange formats supported by `trimesh` (for example OBJ, STL, PLY, GLB/glTF; support depends on installed optional dependencies).
- Builds a simple blockout by replacing each imported mesh/object with its axis-aligned bounding box (AABB).
- Shows a top-down preview of the imported bounds and generated blockout.
- Exports the blockout as OBJ, which Blender can import.
- Can import a neutral JSON scene description, useful as a bridge for future engine-specific extractors or approved runtime/debug exporters.

## What it does NOT do yet

- It does not parse proprietary `.pak`, `.upk`, `.unr`, `.vpk`, or other game archives.
- It does not read or modify a game's process memory.
- It does not automatically reconstruct geometry from screenshots.
- AABB boxes are approximations; rotated objects become larger axis-aligned boxes, and openings/walkable space may be lost.

## Requirements

Python 3.10+ recommended.

```bash
py -m pip install -r requirements.txt
py main.py
```

## Workflow

1. Click **Open geometry…** and select a supported mesh/scene file.
2. Choose whether to create one box per mesh or one box for the entire scene.
3. Click **Build blockout**.
4. Inspect the top-down preview and object statistics.
5. Click **Export OBJ for Blender…**.
6. In Blender: `File > Import > Wavefront (.obj)`.

## Neutral JSON scene format

The importer accepts this simple schema:

```json
{
  "name": "Example level",
  "units": "meters",
  "objects": [
    {
      "name": "Room wall",
      "type": "box",
      "position": [0, 1.5, 0],
      "size": [8, 3, 0.25],
      "rotation_degrees": [0, 0, 0]
    }
  ]
}
```

`position` is the object center, `size` is full width/height/depth, and rotations are Euler angles in degrees. JSON objects are currently converted to axis-aligned boxes; rotation is retained as metadata but not applied to the generated AABB.

## Planned next milestones

1. Engine adapters: Unreal Engine 1 BSP, then one explicitly selected UE3 title, then Source BSP.
2. Preserve actor transforms and collision geometry when an adapter can access them.
3. Add per-object filtering, height slicing, orthographic side views, and measurements.
4. Add an opt-in live-capture bridge based on official modding/debug APIs or user-provided exports.
5. Add Blender collections and metadata export through a generated `.py` script.

Use only game data you own or are authorized to inspect. Prefer official modding tools, documented formats, and offline copies.
