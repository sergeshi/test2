# Architecture notes

## Adapter contract (future)
Each engine adapter should implement a small interface:

- `probe(path) -> confidence + detected format`
- `extract(path) -> NeutralScene`
- `extract_runtime(source) -> NeutralScene` only through a documented/debug/modding bridge
- `diagnostics() -> warnings`

`NeutralScene` should store:
- scene metadata: title, engine guess, source path, unit scale, coordinate basis
- objects: stable id, name, kind, local/world transform, bounds, optional collision triangles
- provenance: source file and parser version
- uncertainty flags: exact / collision-derived / AABB-estimated / reconstructed

## Why AABB first
AABB conversion is robust and easy to inspect, but it loses rotated orientations, holes, thin surfaces, and walkable topology. For real game levels, adapters should preserve BSP/collision triangles where possible and only use AABB for fallback.

## Runtime capture policy
Prefer, in order:
1. official SDK or modding/debug interface
2. documented console command or game-supported map export
3. user-provided capture/telemetry files
4. visual reconstruction as a separate experimental feature

This prototype deliberately does not read arbitrary process memory or bypass game protections.
