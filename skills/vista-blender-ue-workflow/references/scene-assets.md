# Consistent rooms and inspectable props

Use image generation for requested raster concepts. Record a model version only
when the tool exposes it. Choose one architectural identity, then reference an
accepted image for other views. Review mismatched openings, fixtures, stairs and
railings. Image references improve continuity but do not impose geometry; a
generated floor plan is not a measured plan.

Before full construction, define units, north axis, slab elevations, room polygons,
walls, openings, portal IDs, stair rise/run, landings, furniture footprints and
cameras. Derive geometry and views from this shared layout. Check headroom,
landing-to-door connection, wall thickness and paths in the actual model. Do not
let separate room images independently move the same wall or stair.

For a more realistic donor version, inventory its actual actor meshes, slots,
skeletons, animations and lighting. A launcher name is insufficient. Transfer
assets and dependencies to a fresh namespace without overwriting the accepted
map. Record source hashes and use scope. Keep restricted assets/frames outside
model and benchmark payloads; continue other modeling independently.

Blender uses meters; Unreal uses centimeters. Apply scale, preserve pivots, and
measure the imported result. GLB axis conversion belongs in one verified import
step, not ad-hoc rotations on every asset.

- A vessel needs exterior, rounded lip, interior and a sealed bottom. An annular
  bottom can look fine but leak. Test a downward ray from inside and a section view.
- Model close-view wall thickness, seams, joints and edge radii. Texture detail
  cannot repair an incorrect silhouette.
- A single convex collision hull fills a cup cavity. Build appropriate compound
  collision and inspect the actual imported support and inner surfaces.
- Preserve IDs/contact anchors when replacing interactive geometry. A changed
  rim or handle requires regenerated, tested grasp targets.

Use appropriate photo-based PBR sets: albedo in sRGB; roughness, metalness and
normals in linear space. Record texture span/UV density. Poly Haven OpenGL normal
maps need the correct green-channel convention in UE. Read back saved texture
roles: importers can misclassify blue albedo as a normal map.

Skin needs good face/eye/hair geometry, rigging and materials. Higher texture
resolution cannot repair rigid hair or weak facial topology. Distinguish a shader
change from a character asset upgrade.

Render neutral material and in-context views. Inspect glass, contact shadows,
seams and texture scale. Export selected meshes without staging lights/cameras.
Keep source, GLB and render recipe together. Use `--python-exit-code 1`: Blender
can otherwise return 0 after a Python exception. Verify outputs and the manifest.
