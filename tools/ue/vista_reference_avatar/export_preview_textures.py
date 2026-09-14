"""Export existing character texture sources for local Blender review only."""
import hashlib
import json
import os
from pathlib import Path
import unreal

out = Path(os.environ['VISTA_AVATAR_TEXTURE_OUT'])
out.mkdir(parents=True, exist_ok=False)
project = Path(unreal.Paths.project_dir()).resolve()
assert project.parent.name == 'villa-reference-avatar', project
materials = {
    'skin': '/Game/VISTA/HomeMaterialsR4e/Character/M_Skin',
    'eyes': '/Game/VISTA/HomeFidelityR3CharacterH/Materials/M_Eyes',
    'brows': '/Game/VISTA/MakeHumanCC0/R6/VISTA_CC0_Hero_Body_eyebrow001',
    'lashes': '/Game/VISTA/MakeHumanCC0/R6/VISTA_CC0_Hero_Body_eyelashes01',
}
rows = []
registry = unreal.AssetRegistryHelpers.get_asset_registry()
registry.scan_paths_synchronous(['/Game/VISTA'], force_rescan=False)
options = unreal.AssetRegistryDependencyOptions(include_hard_package_references=True,
                                                include_soft_package_references=True)
for role, path in materials.items():
    material = unreal.load_asset(path)
    textures = list(unreal.MaterialEditingLibrary.get_used_textures(material))
    # NullRHI has no compiled material resource: inspect on-disk dependencies.
    pending, seen = [path], set()
    while pending:
        package = pending.pop()
        if package in seen:
            continue
        seen.add(package)
        assert len(seen) < 200, 'Unexpected dependency expansion'
        for dependency in registry.get_dependencies(package, options) or []:
            dep = str(dependency)
            if not dep.startswith('/Game/VISTA/'):
                continue
            asset = unreal.load_asset(dep)
            if isinstance(asset, unreal.Texture2D):
                if asset not in textures:
                    textures.append(asset)
            elif isinstance(asset, unreal.MaterialInterface):
                pending.append(dep)
    assert textures, path
    for texture in textures:
        if not isinstance(texture, unreal.Texture2D):
            continue
        target = out / (role + '-' + texture.get_name() + '.png')
        task = unreal.AssetExportTask()
        task.object = texture
        task.filename = str(target)
        task.automated = True
        task.prompt = False
        task.replace_identical = False
        task.exporter = unreal.TextureExporterPNG()
        assert unreal.Exporter.run_asset_export_task(task), task.errors
        rows.append(dict(role=role, asset=texture.get_path_name(), file=target.name,
                         sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
(out / 'textures.json').write_text(json.dumps(rows, indent=2) + '\n')
