"""A demo can only select the same map/plugin that passed native GPU checks."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from tools.runtime.vista_villa_r1.launch_demo import validate


class VillaDeliveryTests(unittest.TestCase):
    def test_r2_requires_matching_motion_and_visual_acceptance(self):
        with tempfile.TemporaryDirectory(prefix='vista-villa-r1-') as temp:
            root=Path(temp);project=root/'project';project.mkdir()
            uproject=project/'PhotorealHome.uproject';uproject.write_text('{}')
            hashes={}
            for key,relative in [('plugin','Plugins/VistaPhotorealReview/Binaries/Linux/libUnrealEditor-VistaPhotorealReview.so'),
                                 ('map','Content/VISTA/VillaR1/Maps/Villa.umap'),('motion','Content/VISTA/VillaR1/mocap.json')]:
                path=project/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(key.encode())
                hashes[key+'_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
            def save(name,value):
                path=root/(name+'.json');path.write_text(json.dumps(value));return str(path)
            config={'kind':'home','revision':'Villa R2','map':'/Game/VISTA/VillaR1/Maps/Villa','ddc_graph':'VistaVillaR1Cache',
                    'project':str(uproject),'runtime_dir':str(root/'runtime'),'engine':str(uproject),**hashes}
            config['native_proof']=save('functional',{'demo_completed':True,'stairs_reached_upper_floor':True,'placements':1})
            config['native_process']=save('native',{'functional_sequence_passed':True,'hardware_backend_verified':True,**hashes})
            movement={'motion_capture_completed':True,'hardware_backend_verified':True,'motion_proof_sha256':'native-pose-digest','motion_fixed_delta_seconds':1/30,**hashes}
            config['motion_process']=save('movement',movement)
            config['motion_check']=save('joints',{'status':'passed','errors':[],'proof_sha256':'native-pose-digest'})
            visual={'status':'accepted_for_demo',**hashes};config['visual_review']=save('visual',visual)
            self.assertEqual(validate(config),(uproject,root/'runtime'))
            save('movement',{**movement,'motion_sha256':'stale-motion'})
            with self.assertRaisesRegex(ValueError,'different delivery'):validate(config)
            save('movement',movement)
            save('movement',{**movement,'motion_fixed_delta_seconds':0})
            with self.assertRaisesRegex(ValueError,'fixed-step motion sampling'):validate(config)
            save('movement',movement)
            save('joints',{'status':'passed','errors':[],'proof_sha256':'another-run'})
            with self.assertRaisesRegex(ValueError,'different proof'):validate(config)
            save('joints',{'status':'passed','errors':[],'proof_sha256':'native-pose-digest'})
            save('visual',{**visual,'status':'pending'})
            with self.assertRaisesRegex(ValueError,'Visual review'):validate(config)
            save('visual',visual)
            (project/'Content/VISTA/VillaR1/mocap.json').write_bytes(b'unvalidated cycle')
            with self.assertRaisesRegex(ValueError,'Motion delivery changed'):validate(config)

    def test_rejects_changed_or_unvalidated_delivery(self):
        with tempfile.TemporaryDirectory(prefix='vista-villa-r1-') as temp:
            root=Path(temp);project=root/'project';project.mkdir()
            uproject=project/'PhotorealHome.uproject';uproject.write_text('{}')
            plugin=project/'Plugins/VistaPhotorealReview/Binaries/Linux/libUnrealEditor-VistaPhotorealReview.so';plugin.parent.mkdir(parents=True);plugin.write_bytes(b'compiled')
            world=project/'Content/VISTA/VillaR1/Maps/Villa.umap';world.parent.mkdir(parents=True);world.write_bytes(b'accepted geometry')
            proof=root/'proof.json';proof.write_text(json.dumps({'demo_completed':True,'stairs_reached_upper_floor':True,'placements':1}))
            hashes={'plugin_sha256':hashlib.sha256(plugin.read_bytes()).hexdigest(),'map_sha256':hashlib.sha256(world.read_bytes()).hexdigest()}
            process=root/'process.json';accepted={'functional_sequence_passed':True,'hardware_backend_verified':True,**hashes};process.write_text(json.dumps(accepted))
            config={'kind':'home','revision':'Villa R1','map':'/Game/VISTA/VillaR1/Maps/Villa','ddc_graph':'VistaVillaR1Cache',
                'project':str(uproject),'runtime_dir':str(root/'runtime'),'native_proof':str(proof),'native_process':str(process),'engine':str(uproject),**hashes}
            self.assertEqual(validate(config),(uproject,root/'runtime'))
            world.write_bytes(b'untested geometry')
            with self.assertRaisesRegex(ValueError,'Delivery changed'):validate(config)
            world.write_bytes(b'accepted geometry')
            process.write_text(json.dumps({**accepted,'plugin_sha256':'different'}))
            with self.assertRaisesRegex(ValueError,'different delivery'):validate(config)
            process.write_text(json.dumps({**accepted,'hardware_backend_verified':False}))
            with self.assertRaisesRegex(ValueError,'GPU acceptance'):validate(config)
            process.write_text(json.dumps(accepted))
            with self.assertRaisesRegex(ValueError,'Wrong Villa map'):validate({**config,'map':'/Game/VISTA/PhotorealHomeR1/Maps/Home'})


if __name__=='__main__':unittest.main()
