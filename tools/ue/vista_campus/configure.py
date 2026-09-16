"""Select a complete campus revision without depending on a previous revision."""
import json
import re
from pathlib import Path


def select_maps(project: Path, root: str):
    assert project.resolve().parent.name == 'vista-campus'
    assert re.fullmatch(r'/Game/VISTA/CampusR[0-9]+', root)
    names = {'home': 'Home', 'campus': 'Campus', 'gate': 'NorthGate', 'daxue': 'DaxueRoad'}
    for short in names.values():
        assert (project/'Content'/(root.removeprefix('/Game/')+'/Maps/'+short+'.umap')).is_file()
    explorer_path = project/'Config/VistaExplorer.json'
    explorer = json.loads(explorer_path.read_text())
    assert explorer['schema'] == 'vista.explorer/v1'
    assert sorted(s['id'] for s in explorer['scenes']) == sorted(names)
    for scene in explorer['scenes']:
        scene['map'] = root+'/Maps/'+names[scene['id']]
    home_path = project/'Config/VistaHomeActions.json'
    home = json.loads(home_path.read_text())
    home['scene_map'] = root+'/Maps/Home'
    engine_path = project/'Config/DefaultEngine.ini'
    engine, count = re.subn(r'(?m)^(GameDefaultMap|EditorStartupMap)=.*$',
        lambda m: m.group(1)+'='+root+'/Maps/Campus', engine_path.read_text())
    assert count == 2
    explorer_path.write_text(json.dumps(explorer, indent=2)+'\n')
    home_path.write_text(json.dumps(home, indent=2)+'\n')
    engine_path.write_text(engine)
