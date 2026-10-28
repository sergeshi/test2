# Runtime capture bridge

## What this adds

The desktop app can receive scene snapshots while a game is running. In the app, click **Start local runtime bridge**. The receiver binds only to `127.0.0.1:47831` and accepts newline-delimited JSON.

This is a transport and normalization layer, not a universal game extractor. A game-specific adapter still needs to obtain object transforms or collision bounds through an authorized source such as an official SDK, modding API, developer console/plugin, or permitted debug exporter. The bridge does not inspect process memory, inject code, or bypass anti-cheat.

## Test the connection

From the repository root:

1. Install dependencies: `py -m pip install -r requirements.txt`.
2. Start the desktop app: `py main.py`.
3. Click **Start local runtime bridge**.
4. In a second terminal, run `py examples/send_runtime_snapshot.py`.
5. The UI should load a seven-object demo corridor. Build a blockout and export OBJ as usual.

## JSON protocol

Send one complete JSON object per line, encoded as UTF-8. Supported fields:

- `name`: level name.
- `source`: adapter/exporter label.
- `units`: coordinate units, e.g. `cm`, `m`, or `uu`.
- `objects`: list of objects. Each object uses either `position` + `size` or `bounds`.

Example:

```json
{
  "name": "Captured level",
  "source": "my-game adapter",
  "units": "cm",
  "objects": [
    {"name": "Floor", "type": "collision", "position": [0, 0, -20], "size": [1200, 800, 40]},
    {"name": "Wall", "type": "static_mesh", "bounds": [[-600, -400, 0], [600, -380, 300]]}
  ]
}
```

`position` is the center, `size` is the full XYZ size, and `bounds` contains minimum and maximum XYZ corners. For a clean blockout, export collision volumes and level geometry bounds where available.

## Next adapter milestone

Pick a target game/engine and implement a small exporter for it. Unreal Engine's Python scripting API is editor-oriented; a packaged game usually needs an in-project C++/Blueprint plugin or an existing supported modding interface. Avoid assuming one adapter will work for every UE3/UE4 title.
