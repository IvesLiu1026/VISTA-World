"""Calibrate the private water material for transparent close viewing."""
import json
import os
from pathlib import Path
import unreal

out=Path(os.environ['VISTA_VILLA_WATER_OUT'])
if out.exists() or 'vista-villa-r1-' not in str(Path(unreal.Paths.project_dir()).resolve()):raise RuntimeError('Fresh private revision required')
L=unreal.MaterialEditingLibrary;A=unreal.EditorAssetLibrary
m=unreal.load_asset('/Game/VISTA/VillaR1/Fluids/M_VesselWater')
f=L.create_material_expression(m,unreal.MaterialExpressionFresnel)
mix=L.create_material_expression(m,unreal.MaterialExpressionLinearInterpolate)
mix.set_editor_property('const_a',.15);mix.set_editor_property('const_b',.55)
assert L.connect_material_expressions(f,'',mix,'Alpha')
assert L.connect_material_property(mix,'',unreal.MaterialProperty.MP_OPACITY)
L.recompile_material(m);assert A.save_loaded_asset(m,only_if_is_dirty=False)
out.write_text(json.dumps({'material':m.get_path_name(),'normal_opacity':.15,'grazing_opacity':.55,'preserved_demo_modified':False},indent=2)+'\n')
