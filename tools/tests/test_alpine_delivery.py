"""Delivery validation only. These temporary files are synthetic unit fixtures."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from runtime.vista_alpine_r3.launch_demo import validate

def write(path,data):path.write_text(json.dumps(data));return str(path)

class AlpineDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='vista-villa-r3-delivery-');self.root=Path(self.temp.name)
        self.project=self.root/'demo-project-test';self.project.mkdir();(self.project/'PhotorealHome.uproject').write_text('{}')
        paths={'plugin_sha256':'Plugins/VistaPhotorealReview/Binaries/Linux/libUnrealEditor-VistaPhotorealReview.so',
               'map_sha256':'Content/VISTA/VillaR1/Maps/Villa.umap','motion_sha256':'Content/VISTA/VillaR1/mocap.json',
               'alpine_motion_sha256':'Content/VISTA/AlpineR3/locomotion.json','appearance_sha256':'Content/VISTA/VillaR1/appearance.json'}
        self.hashes={}
        for k,rel in paths.items():
            p=self.project/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(k.encode());self.hashes[k]=hashlib.sha256(p.read_bytes()).hexdigest()
        self.config={'kind':'home','revision':'Alpine Villa R3','map':'/Game/VISTA/VillaR1/Maps/Villa','ddc_graph':'VistaAlpineR3Cache',
                     'project':str(self.project/'PhotorealHome.uproject'),'runtime_dir':str(self.root/'runtime'),**self.hashes}
        movement={**self.hashes,'exit_code':0,'hardware_backend_verified':True,'purpose':'movement_and_visual_acceptance',
                  'fixed_delta_seconds':1/30,'alpine_capture_completed':True,'alpine_proof_sha256':'fixture-proof'}
        self.config['alpine_process']=write(self.root/'movement.json',movement)
        self.config['native_process']=write(self.root/'kitchen.json',{**self.hashes,'exit_code':0,'hardware_backend_verified':True,'functional_sequence_passed':True})
        self.config['alpine_check']=write(self.root/'check.json',{'status':'passed','errors':[],'proof_sha256':'fixture-proof'})
        self.config['motion_process']=write(self.root/'posture.json',{**self.hashes,'exit_code':0,'hardware_backend_verified':True,
            'motion_capture_completed':True,'motion_fixed_delta_seconds':1/30,'motion_proof_sha256':'posture-fixture'})
        self.config['motion_check']=write(self.root/'posture-check.json',{'status':'passed','errors':[],'proof_sha256':'posture-fixture'})
        self.config['visual_review']=write(self.root/'visual.json',{**self.hashes,'status':'accepted_for_demo'})
        rows=[{'file':str(p.relative_to(self.project)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in self.project.rglob('*') if p.is_file()]
        m=self.root/'frozen.json';self.config['frozen_manifest']=write(m,{'files':rows});self.config['frozen_manifest_sha256']=hashlib.sha256(m.read_bytes()).hexdigest()
        engine=self.root/'engine-fixture';engine.write_text('not executable');self.config['engine']=str(engine)

    def tearDown(self):self.temp.cleanup()

    def test_matching_frozen_delivery(self):self.assertEqual(validate(self.config)[0],self.project/'PhotorealHome.uproject')

    def test_visual_preview_is_not_motion_evidence(self):
        path=Path(self.config['alpine_process']);data=json.loads(path.read_text());data['purpose']='visual_preview';data['fixed_delta_seconds']=.1;write(path,data)
        with self.assertRaisesRegex(ValueError,'visual preview'):validate(self.config)

    def test_unlisted_asset_is_rejected(self):
        (self.project/'Content/extra.uasset').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'inventory'):validate(self.config)

    def test_inconsistent_native_proof_is_rejected(self):
        path=Path(self.config['native_process']);data=json.loads(path.read_text());data['appearance_sha256']='other-body';write(path,data)
        with self.assertRaisesRegex(ValueError,'different delivery'):validate(self.config)

    def test_mismatched_stance_check_is_rejected(self):
        path=Path(self.config['motion_check']);data=json.loads(path.read_text());data['proof_sha256']='previous-character';write(path,data)
        with self.assertRaisesRegex(ValueError,'Posture/stance'):validate(self.config)

if __name__=='__main__':unittest.main()
