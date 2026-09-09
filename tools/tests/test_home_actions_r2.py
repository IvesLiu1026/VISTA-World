import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]


def module(name):
    path=ROOT/'tools/runtime/vista_home_actions_r2'/f'{name}.py'
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


class HomeActionsContracts(unittest.TestCase):
    def test_all_event_entities_bound_and_sources_unchanged(self):
        build=module('build_contract');data=build.build()
        ids=[r['id'] for r in data['entities']]
        self.assertEqual(len(ids),len(set(ids)))
        self.assertEqual(len({r['room'] for r in data['entities']}),6)
        for event in data['events']:
            self.assertTrue(set(event['participating_entity_ids'])<=set(ids))
            self.assertEqual(event,json.loads((build.SOURCE/'events'/f'{event["event_id"]}.json').read_text()))
        self.assertEqual(data,json.loads((ROOT/'world_packs/vista_photoreal_home_r2/scene.json').read_text()))

    def test_storage_roles_and_visible_controls(self):
        data=module('build_contract').build()
        for entity in data['entities']:
            if entity['kind']=='container':
                self.assertTrue(entity['storage_cm'])
                self.assertTrue(all(v>0 for v in entity['capacity_cm']))
                self.assertEqual(entity['initial_state']['contents'],[])
            if entity['kind']=='pickup':
                self.assertGreater(entity['mass'],0)
                self.assertGreater(entity['height'],0)
        washer=next(r for r in data['entities'] if r['short_id']=='washer')
        self.assertIn('turn_on',washer['actions']);self.assertNotIn('press_button',washer['actions'])

    def test_restricted_input_never_inherits_privileged_fields(self):
        exporter=module('export_review')
        row={'turn_id':'1','speaker':'user','text':'I am heading out.','start_sec':0,'end_sec':2,
             'render_script':'SECRET_SENTINEL','oracle':{'label':'SECRET_SENTINEL'},'event_id':'mmg_001','review_note':'SECRET_SENTINEL'}
        result=exporter.restricted_input('opaque-case',[row])
        text=json.dumps(result)
        self.assertNotIn('SECRET_SENTINEL',text);self.assertNotIn('mmg_001',text)
        self.assertNotIn('start_sec',result['dialogue'][0])
        self.assertEqual(result['source_paths'],{'video':'observation.mp4'})
        self.assertFalse(result['allowed_information']['can_use_oracle'])
        with self.assertRaises(ValueError):exporter.normalize_dialogue([row],3)

    def test_dialogue_timing_and_identity_are_validated(self):
        exporter=module('export_review');row={'turn_id':'1','speaker':'user','text':'Hello.','start_sec':0,'end_sec':2}
        self.assertEqual(exporter.normalize_dialogue([row],3),[row])
        timed=exporter.restricted_input('opaque',[row],timed=True)
        self.assertEqual(timed['dialogue'][0]['start_sec'],'0')
        self.assertTrue(all(isinstance(v,str) for v in timed['dialogue'][0].values()))
        for bad in [float('nan'),-1,4,True]:
            r=copy.deepcopy(row);r['end_sec']=bad
            with self.assertRaises(ValueError):exporter.normalize_dialogue([r],3)
        with self.assertRaises(ValueError):exporter.normalize_dialogue([row,row],3)


if __name__=='__main__':unittest.main()
