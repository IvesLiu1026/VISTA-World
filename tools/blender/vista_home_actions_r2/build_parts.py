"""Separate the authored home into operable assemblies; never edit the source blend."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vista_photoreal_r1'))
import build_kitchen as k


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--only',nargs='+')
    a = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
    if a.out.exists():
        raise RuntimeError('Use a fresh modeling attempt')
    (a.out / 'glb').mkdir(parents=True)
    bpy.ops.wm.open_mainfile(filepath=str(a.source))
    k.OUT = a.out
    k.MATERIALS = {m.name.removeprefix('PR_'): m for m in bpy.data.materials}
    groups = {}
    for o in bpy.context.scene.objects:
        if o.type in ('MESH', 'CURVE') and o.get('part'):
            groups.setdefault(o['part'], []).append(o)
    changed = set()
    parts = []

    def split(old, name, prefixes, pivot=None, predicate=None):
        selected = [o for o in groups[old] if any(o.name.startswith(s) for s in prefixes)
                    and (predicate is None or predicate(o))]
        if not selected:
            raise RuntimeError('Missing authored geometry: ' + name)
        groups[old] = [o for o in groups[old] if o not in selected]
        groups[name] = selected
        changed.update([old, name])
        if pivot is not None:
            pivots[name] = pivot
        for o in selected:
            o['part'] = name
        return selected

    pivots = {}
    # The original blanket extends 40 cm horizontally beyond the mattress.
    # Drape that excess down at the bed edge, leaving a usable wardrobe aisle.
    for o in groups['bedroom_bed']:
        if not o.name.startswith(('Draped cotton duvet','Duvet stitched side hem')):continue
        inverse=o.matrix_world.inverted()
        points=list(o.data.vertices) if o.type=='MESH' else [p for s in o.data.splines for p in s.points]
        for v in points:
            w=o.matrix_world @ v.co.xyz
            if w.y<1.60:
                w.y=1.57-(1.60-w.y)*.06
                local=inverse @ w
                if o.type=='MESH':v.co=local
                else:v.co=(*local,1)
    changed.add('bedroom_bed')
    split('entry_shoe_bench', 'keys', ['Key ring', 'House key', 'Key tooth'])
    split('entry_slippers', 'slipper', ['House slipper'], predicate=lambda o: o.location.y < -3.2)
    split('bedroom_nightstand', 'phone', ['Smartphone', 'Phone glass'])
    split('bedroom_nightstand', 'bedside_drawer', ['Nightstand drawer', 'Drawer pull'])
    split('bathroom_vanity','basin_control',['Basin lever'],(1.345,5.15,.968))
    split('bathroom_toilet','flush_control',['Dual flush button'])
    split('living_media','tv_screen',['TV glass face'])
    split('office_desk','computer_screen',['Monitor screen'])
    split('living_lamp','lamp_bulb',['Lamp bulb'])
    split('bedroom_backpack', 'backpack', ['Charcoal backpack', 'Backpack zip', 'Backpack top', 'Backpack shoulder', 'Pocket zipper'])
    split('office_storage', 'box', ['Cardboard storage box', 'Box lid', 'Box finger slot'])
    for side, x in [('left', 2.644), ('right', 3.036)]:
        split('office_storage', 'cabinet_' + side, ['Storage lower door', 'Cabinet knob'],
              (x + (.191 if side=='right' else -.191), 3.459, .058), lambda o, x=x: abs(o.location.x - x) < .18)
    # Four independent wardrobe leaves; each has a real hinge and handle.
    for i in range(4):
        x = -4.30 + (i - 1.5) * .60
        split('bedroom_wardrobe', 'wardrobe_' + str(i), ['Wardrobe door', 'Wardrobe brushed pull'],
              (x - .296, .718, .062), lambda o, x=x: abs(o.location.x - x) < .25 if o.type == 'MESH' else
              abs(sum((o.matrix_world @ p.co.xyz).x for s in o.data.splines for p in s.points) /
                  max(1, sum(len(s.points) for s in o.data.splines)) - x) < .30)
    split('bathroom_basket', 'basket_lid', ['Laundry basket lid', 'Basket lid handle'], (.98, 6.285, .53))
    split('bathroom_washer', 'washer_door', ['Washer circular door trim', 'Washer door handle'], (.681, 7.35, .425))
    groups['washer_door'] += groups.pop('bathroom_washer_glass')
    changed.add('bathroom_washer_glass')
    split('bathroom_washer', 'washer_control', ['Program selector', 'Washer button'], (.707, 7.13, .78))
    # Replace the solid front/body occluders with an actual open drum cavity.
    removed = [o for o in groups['bathroom_washer'] if o.name.startswith(
        ('Washer metal cabinet', 'Washer front panel', 'Door seal', 'Drum recessed dark'))]
    groups['bathroom_washer'] = [o for o in groups['bathroom_washer'] if o not in removed]
    for o in removed:
        bpy.data.objects.remove(o, do_unlink=True)
    before = set(bpy.context.scene.objects)
    for y in [6.83, 7.43]: k.box('Washer side shell', (.61,.018,.82),(1.06,y,.438),'WhiteEnamel','washer_shell')
    k.box('Washer rear shell',(.018,.60,.82),(1.356,7.13,.438),'WhiteEnamel','washer_shell')
    for z, h in [(.045,.05),(.767,.145)]: k.box('Washer front bridge',(.026,.586,h),(.75,7.13,z),'WhiteEnamel','washer_shell')
    for y in [6.859,7.401]: k.box('Washer front margin',(.026,.044,.65),(.75,y,.385),'WhiteEnamel','washer_shell')
    rim = k.lathe('Rubber drum bellows',[(.180,-.04),(.216,-.04),(.224,0),(.209,.025),(.181,.025),(.180,-.04)],(0,0,0),'Black','washer_shell',96)
    rim.rotation_euler[1] = math.pi / 2
    rim.location = (.726,7.13,.425)
    drum = k.lathe('Open brushed steel drum',[(.001,.27),(.174,.27),(.178,.25),(.178,0),(.174,0),(.172,.25),(.001,.25)],(0,0,0),'Steel','washer_shell',96)
    drum.rotation_euler[1] = math.pi / 2
    drum.location = (.733,7.13,.425)
    groups['bathroom_washer'] += [o for o in bpy.context.scene.objects if o not in before]
    changed.add('bathroom_washer')
    # The old scene's tub mixer was behind fixed shower glass. A reachable
    # deck-mounted control at the open end permits an honest hand path.
    old = [o for o in groups['bathroom_tub'] if o.name.startswith(('Bath mixer', 'Thermostatic mixer', 'Bath faucet'))]
    groups['bathroom_tub'] = [o for o in groups['bathroom_tub'] if o not in old]
    for o in old: bpy.data.objects.remove(o, do_unlink=True)
    k.PARTS = {}
    k.cylinder('Deck mixer base',.030,.15,(-.65,6.30,.63),'Chrome','bath_tap')
    k.tube('Deck bath spout',[(-.65,6.30,.69),(-.76,6.30,.73),(-.89,6.30,.73),(-.92,6.30,.68)],.018,'Chrome','bath_tap')
    k.tube('Bath flow lever',[(-.65,6.30,.72),(-.58,6.30,.745)],.009,'Chrome','tap_control')
    pivots['tap_control'] = (-.65,6.30,.72)
    for name, obs in k.PARTS.items(): groups[name] = obs; changed.add(name)
    k.PARTS={}
    k.cylinder('Television power button',.006,.004,(-4.03,-3.567,.563),'Black','tv_control','Y',24)
    k.cylinder('Monitor power button',.006,.004,(6.157,1.80,.873),'Black','computer_control','X',24)
    k.box('Lamp inline switch',(.025,.027,.047),(-5.75,-.47,1.10),'Black','lamp_control',.004)
    k.box('Lamp rocker',(.016,.004,.021),(-5.75,-.453,1.10),'Steel','lamp_control',.002)
    for name, obs in k.PARTS.items():groups[name]=obs;changed.add(name)
    changed.add('bathroom_tub')
    split('kitchen_cabinets', 'stove_control', ['Hob control knob'], (3.875,-.620,.949),
          lambda o: abs(o.location.x-3.875)<.01)
    before=set(bpy.context.scene.objects)
    k.box('Stove knob index',(.003,.011,.0012),(3.875,-.625,.949),'WhiteEnamel','stove_control',.0003)
    groups['stove_control'] += [o for o in bpy.context.scene.objects if o not in before]
    # Author closed door leaves independently of the fixed frames.
    for name in ['living', 'kitchen', 'bedroom', 'office', 'bathroom']:
        for o in groups.pop(name + '_door'): bpy.data.objects.remove(o, do_unlink=True)
        changed.add(name + '_door')
    split('entry_front_door', 'old_entry_leaf', ['Front entrance door','Entrance raised panel','Peephole','Entrance handle'])
    for o in groups.pop('old_entry_leaf'): bpy.data.objects.remove(o, do_unlink=True)
    changed.remove('old_entry_leaf')
    door_specs = [('entry',(-.525,-3.904,0),0,1.05),
                  ('living',(-1.59,-1.49,0),-math.pi/2,1.0),('kitchen',(1.59,-1.49,0),-math.pi/2,1.0),
                  ('bedroom',(-1.59,2.51,0),-math.pi/2,1.0),('office',(1.59,2.51,0),-math.pi/2,1.0),
                  ('bathroom',(-.51,4.09,0),0,1.0)]
    for name, pivot, angle, width in door_specs:
        key = 'action_door_' + name
        before = set(bpy.context.scene.objects)
        k.box('Operable oak leaf', (width,.040,2.09),(width/2,0,1.045),'DoorOak',key,.004)
        for side in [-1,1]:
            k.box('Inset oak panel',(width-.14,.008,1.78),(width/2,side*.023,1.08),'Oak',key,.004)
            k.cylinder('Handle rosette',.023,.010,(width-.10,side*.030,1.02),'Steel',key,'Y',32)
            k.tube('Operable lever',[(width-.1,side*.031,1.02),(width-.1,side*.073,1.02),(width-.20,side*.073,1.02)],.009,'Steel',key)
        obs = [o for o in bpy.context.scene.objects if o not in before]
        matrix = Matrix.Translation(Vector(pivot)) @ Matrix.Rotation(angle,4,'Z')
        for o in obs: o.matrix_world = matrix @ o.matrix_world
        groups[key] = obs; pivots[key] = pivot; changed.add(key)
    # Existing pot and lid acquire bottom origins; no design replacement.
    for name in ['kitchen_pot','kitchen_lid','office_chair','office_ladder']:
        changed.add(name)
    # New physical jug and folded laundry reuse the home's authored materials.
    k.PARTS = {}
    origin = (3.48,-2.82,.767)
    k.lathe('Glazed water jug',[(0,0),(.068,0),(.075,.015),(.082,.14),(.070,.22),(.073,.25),(.067,.253),(.062,.22),(.074,.14),(.067,.015),(0,.012)],origin,'Ceramic','jug',96)
    k.tube('Jug handle',[(3.553,-2.82,.94),(3.59,-2.82,.95),(3.61,-2.82,.89),(3.58,-2.82,.82),(3.551,-2.82,.82)],.009,'Ceramic','jug')
    pivots['jug']=origin
    for i in range(4):
        k.box('Folded cotton laundry',(.27,.23,.018),(.98,6.10,.055+i*.021),'Cotton','clothes',.008)
    k.tube('Cotton folded hem',[(.86,5.99,.135),(.98,5.985,.135),(1.10,5.99,.135)],.002,'Cotton','clothes')
    for name, obs in k.PARTS.items(): groups[name] = obs; changed.add(name)
    # Replace the folded decorative ladder with a deployed A-frame. Rear
    # stiles actually meet their hinges and all four feet contact the floor.
    for o in groups['office_ladder']:bpy.data.objects.remove(o,do_unlink=True)
    k.PARTS = {}
    x=2.84
    for dx in [-.22,.22]:
        k.tube('Ladder front stile',[(x+dx,2.65,.04),(x+dx,3.04,1.40)],.022,'Steel','ladder_platform')
        k.tube('Ladder deployed rear stile',[(x+dx,3.25,.04),(x+dx,3.04,1.38)],.022,'Steel','ladder_platform')
        for y in [2.65,3.25]:k.box('Ladder rubber foot',(.06,.065,.05),(x+dx,y,.025),'Black','ladder_platform',.008)
        k.tube('Ladder spreader brace',[(x+dx,2.78,.5),(x+dx,3.17,.5)],.012,'Steel','ladder_platform')
    for z in [.25,.51,.77]:
        y=2.65+z*.285
        k.box('Ladder non-slip tread',(.405,.18,.024),(x,y,z),'Steel','ladder_platform',.003)
        for j in range(6):k.box('Ladder tread grip',(.38,.007,.002),(x,y-.075+j*.03,z+.013),'Black','ladder_platform',.0004)
    k.box('Ladder standing platform',(.405,.34,.025),(x,2.97,1.045),'Steel','ladder_platform',.004)
    k.tube('Ladder upper handrail',[(x-.22,3.04,1.36),(x-.19,3.04,1.49),(x+.19,3.04,1.49),(x+.22,3.04,1.36)],.022,'Steel','ladder_platform')
    groups['office_ladder']=k.PARTS['ladder_platform']
    # Save named parts in the source copy, with packed materials retained.
    for name in sorted(changed):
        if a.only and name not in a.only:continue
        obs = groups.get(name, [])
        if not obs: continue
        if name not in pivots:
            points=[]
            deps=bpy.context.evaluated_depsgraph_get()
            for o in obs:
                evaluated=o.evaluated_get(deps)
                points.extend(evaluated.matrix_world @ Vector(v) for v in evaluated.bound_box)
            low=Vector(tuple(min(v[i] for v in points) for i in range(3)))
            high=Vector(tuple(max(v[i] for v in points) for i in range(3)))
            pivots[name]=((low.x+high.x)/2,(low.y+high.y)/2,low.z)
        row=k.export_part(name,obs,pivots[name]);parts.append(row)
        for o in obs:o['part']=name
    bpy.ops.wm.save_as_mainfile(filepath=str(a.out/'home-actions.blend'))
    report={'schema':'vista.home-action-parts/v1','source':str(a.source),
            'source_sha256':hashlib.sha256(a.source.read_bytes()).hexdigest(),
            'remove_labels':['PR_'+s for s in sorted(changed) if not a.only or s in a.only] + ([] if a.only else ['PR_bathroom_washer_glass']),
            'partial_export':bool(a.only),
            'parts':parts,'blend':str(a.out/'home-actions.blend')}
    (a.out/'parts.json').write_text(json.dumps(report,indent=2)+'\n')
    print('HOME_ACTION_PARTS_READY',len(parts))


if __name__=='__main__':main()
