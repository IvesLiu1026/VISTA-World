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

## Saved imports and large interiors

Save the whole Interchange dependency subtree before renaming or checkpointing
the mesh. Interrupted authoring can leave a mesh whose materials or skeleton
were never saved. Reopen in a fresh process and inspect actual slots/references;
file existence alone is insufficient for safe resume.

Use `InterchangeManager.import_asset` with automated, no-dialog parameters and
explicit saves in headless UE. `AssetImportTask` can invoke a Slate save dialog
even after a successful import. Check every material-connection return value.
NullRHI cannot catch a broken Vulkan shader: inspect the GPU log for fallbacks.

Keep walls, ceilings and slabs as separate meshes for Lumen surface coverage.
For geometry revisions with a verified native palette, Blender's `VIEWPORT`
material export retains names without copying every photograph. `PLACEHOLDER`
omits those bindings. Verify UVs, map named slots to the real materials, save
them on the mesh, and only then enable Nanite on appropriate opaque geometry.

A continuous counter needs deliberate UV placement within a photographed slab.
Do not magnify a tiny 2K crop into a hero surface. Use adequate source resolution
and separately modeled floor joints; inspect close and room views. Match light
color, exposure and proportions against the same approved design images.

If the exterior clips while stairs remain dark, separate exposure/direct-sun
balance from the architecture's access to daylight. Model actual wall/roof
openings, jambs, sills, frames and glazing; a light above a sealed slab does not
create a skylight. Trace both storeys and preserve stair support, clear width,
landings and guards. Window-associated rect lights may approximate indirect
bounce, but label the approximation. Compare the same native cameras before and
after, then add eye-height views of the stair and landing themselves; a gallery
camera aimed down at the living room cannot establish gallery lighting quality.
