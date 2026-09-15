"""Repair only this task's clutter using actual rendered support geometry."""
import json
import os
from pathlib import Path
import unreal
p=Path(unreal.Paths.project_dir()).resolve();assert p.parent.name.startswith('six-room-companion-dev-stream-')
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert level.load_level('/Game/VISTA/CampusR25/Maps/Home');world=unreal.EditorLevelLibrary.get_editor_world()
owned={a.get_actor_label():a for a in actors.get_all_level_actors() if a.get_actor_label().startswith('Streaming_')}
assert len(owned)==16
# Commandlet worlds lack the live collision scene. Query the saved render
# triangles directly; no change to original furniture collision settings.
surfaces=[a for a in actors.get_all_level_actors() if isinstance(a,unreal.StaticMeshActor)]
path=p/'Config/VistaHomeActions.json';contract=json.loads(path.read_text())
shifts={'daily_1':(1022,-38,52),'daily_2':(1022,-133,52),'daily_3':(311,-362,51),
        'daily_10':(993,-1046,395),'daily_11':(993,-1046,399),'daily_13':(1350,-1113,429),
        'daily_14':(1360,-887,408)}
yaws={'daily_1':20,'daily_3':0,'daily_5':14,'daily_8':8,'daily_10':-6,'daily_11':9}
done=[];rows=[]
for e in contract['entities']:
    a=owned.get(e['label'])
    if not a:continue
    short=e['short_id'];pos=a.get_actor_location();x,y,z=shifts.get(short,(pos.x,pos.y,pos.z))
    a.set_actor_rotation(unreal.Rotator(pitch=0,yaw=yaws.get(short,0),roll=0),False)
    a.set_actor_location(unreal.Vector(x,y,z),False,True)
    ignore=[v for v in owned.values() if v not in done]
    candidates=[]
    for surface in surfaces:
        if surface in ignore:continue
        o,extent=surface.get_actor_bounds(False)
        if abs(x-o.x)>extent.x+.2 or abs(y-o.y)>extent.y+.2:continue
        hit=unreal.HomeActionsAuthoring.static_support_point(surface,unreal.Vector(x,y,z))
        if hit.z>-9000:candidates.append((hit.z,surface.get_actor_label()))
    assert candidates,(short,'no rendered support')
    support,label=max(candidates);impact=unreal.Vector(x,y,support)
    origin,extent=a.get_actor_bounds(False)
    bottom_offset=origin.z-extent.z-z
    height=impact.z-bottom_offset+.06
    a.set_actor_location(unreal.Vector(x,y,height),False,True)
    e['control_cm']=[x,y,height+(e.get('grip_height',0) if e['kind']=='pickup' else 1)]
    rows.append({'label':a.get_actor_label(),'location_cm':[x,y,height],'support_cm':[impact.x,impact.y,impact.z],'support_actor':label,'method':'render_triangle_projection','bottom_gap_cm':.06})
    done.append(a)
assert level.save_current_level();path.write_text(json.dumps(contract,ensure_ascii=False,indent=2)+'\n')
Path(os.environ['VISTA_STREAM_SETTLED']).write_text(json.dumps(rows,indent=2)+'\n')
