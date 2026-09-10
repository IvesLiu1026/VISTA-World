"""Regression checks for exclusive review input and restoration on failure."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location("review_session",Path(__file__).with_name("review_session.py"))
review=importlib.util.module_from_spec(spec);spec.loader.exec_module(review)


class ReviewSelectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.state=self.root/"input-selection.json"
        self.units=set();self.calls=[]
        patches={"KIND":"home","GAME":review.REVIEWS["home"][0],"RELAY":review.REVIEWS["home"][1],"TITLE":review.REVIEWS["home"][2],"MAP":review.REVIEWS["home"][3],"SELECTION":self.root/"selection.json"}
        for name,value in patches.items():
            p=patch.object(review,name,value);p.start();self.addCleanup(p.stop)
        p=patch.object(review,"active",side_effect=lambda unit:unit in self.units);p.start();self.addCleanup(p.stop)
        p=patch.object(review,"run",side_effect=self.fake_run);p.start();self.addCleanup(p.stop)

    def fake_run(self,args,check=True):
        self.calls.append(args)
        if args[:3]==["systemctl","--user","stop"]:self.units.discard(args[3])
        if args[:3]==["systemctl","--user","start"]:self.units.add(args[3])
        if args[0]=="systemd-run":self.units.add(next(x.split("=",1)[1] for x in args if x.startswith("--unit=")))

    def test_select_home_preserves_external_demo_and_excludes_kitchen_input(self):
        kg,kr,_,_=review.REVIEWS["kitchen"]
        self.units.update([kg,kr,review.GAME,review.PREVIOUS_RELAY,"vista-playable-actions-fast-candidate-r23.service"])
        with patch.object(review,"focus_review",return_value=123):
            review.start({"runtime_dir":str(self.root)},self.state)
        self.assertNotIn(kg,self.units);self.assertNotIn(kr,self.units)
        self.assertNotIn(review.PREVIOUS_RELAY,self.units)
        self.assertIn(review.RELAY,self.units)
        self.assertIn("vista-playable-actions-fast-candidate-r23.service",self.units)
        self.assertTrue(json.loads(self.state.read_text())["previous_relay_active"])

    def test_late_peer_stop_does_not_restore_a_second_input_relay(self):
        kg,kr,_,_=review.REVIEWS["kitchen"]
        self.units.update([review.GAME,review.RELAY,kg,kr])
        self.state.write_text(json.dumps({"previous_relay_active":True}))
        review.stop(self.state)
        self.assertIn(kg,self.units);self.assertIn(kr,self.units)
        self.assertNotIn(review.PREVIOUS_RELAY,self.units)

    def test_home_bridge_and_ddc_are_opt_in_per_fresh_session(self):
        profile={"runtime_dir":str(self.root),"engine":"/engine","project":"/project",
                 "ddc_graph":"VistaHomeActionsCache","home_actions_bridge":True}
        with patch.object(review,"focus_review",return_value=123):review.start(profile,self.state)
        command=next(c for c in self.calls if c[0]=="systemd-run" and "--unit="+review.GAME in c)
        self.assertIn("-ddc=VistaHomeActionsCache",command)
        user=next(c.removeprefix("-UserDir=") for c in command if c.startswith("-UserDir="))
        self.assertIn("-VistaHomeBridge="+str(Path(user)/"home-bridge"),command)

    def test_original_profiles_keep_original_cache_and_no_bridge(self):
        with patch.object(review,"focus_review",return_value=123):
            review.start({"runtime_dir":str(self.root),"engine":"/engine","project":"/project"},self.state)
        command=next(c for c in self.calls if c[0]=="systemd-run" and "--unit="+review.GAME in c)
        self.assertIn("-ddc=InstalledNoZenLocalFallback",command)
        self.assertFalse(any(c.startswith("-VistaHomeBridge=") for c in command))
        self.assertNotIn("--ro-bind",command)
        self.assertFalse(any("VirtualTextureChunkDDCCache" in c for c in command))

    def test_frozen_alpine_assets_stay_read_only_with_external_vt_cache(self):
        frozen=self.root/"demo-project-a";frozen.mkdir()
        project=frozen/"PhotorealHome.uproject";project.touch()
        profile={"runtime_dir":str(self.root),"engine":"/engine","project":str(project),
                 "map":"/Game/VISTA/VillaR1/Maps/Villa","ddc_graph":"VistaAlpineR3Cache",
                 "frozen_manifest":str(self.root/"frozen-files.json")}
        with patch.object(review,"focus_review",return_value=123):review.start(profile,self.state)
        command=next(c for c in self.calls if c[0]=="systemd-run" and "--unit="+review.GAME in c)
        mount=command.index("--ro-bind")
        self.assertEqual(command[mount+1:mount+3],[str(frozen),str(frozen)])
        self.assertLess(mount,command.index("--"))
        user=Path(next(c.removeprefix("-UserDir=") for c in command if c.startswith("-UserDir=")))
        cache=Path(next(c.split(":Path=",1)[1] for c in command if "VirtualTextureChunkDDCCache" in c))
        self.assertTrue(cache.is_relative_to(user))
        self.assertFalse(cache.is_relative_to(frozen))

    def test_villa_selects_its_map_without_enabling_the_old_apartment(self):
        profile={"runtime_dir":str(self.root),"engine":"/engine","project":"/villa",
                 "map":"/Game/VISTA/VillaR1/Maps/Villa","ddc_graph":"VistaVillaR1Cache","exposure_offset":0}
        with patch.object(review,"focus_review",return_value=123):review.start(profile,self.state)
        command=next(c for c in self.calls if c[0]=="systemd-run" and "--unit="+review.GAME in c)
        self.assertIn(profile["map"],command);self.assertIn("-ddc=VistaVillaR1Cache",command)
        self.assertNotIn("-VistaWholeHome",command);self.assertNotIn(review.REVIEWS["home"][3],command)

    def test_unknown_map_is_rejected_before_selection_changes(self):
        with self.assertRaisesRegex(ValueError,"Unknown reviewed map"):
            review.start({"map":"/Game/Unreviewed","runtime_dir":str(self.root)},self.state)
        self.assertFalse(self.calls);self.assertFalse(self.state.exists())

    def test_failed_window_start_restores_original_input(self):
        self.units.update([review.GAME,review.PREVIOUS_RELAY])
        engine=self.root/"engine";engine.touch()
        project=self.root/"project";project.touch()
        profile=self.root/"profile.json"
        profile.write_text(json.dumps({"kind":"home","engine":str(engine),"project":str(project),"runtime_dir":str(self.root)}))
        with patch("sys.argv",["review_session","--profile",str(profile)]), patch.object(review,"focus_review",return_value=None), patch.object(review.time,"monotonic",side_effect=[0,200]):
            with self.assertRaisesRegex(RuntimeError,"window did not become ready"):review.main()
        self.assertNotIn(review.GAME,self.units)
        self.assertNotIn(review.RELAY,self.units)
        self.assertIn(review.PREVIOUS_RELAY,self.units)
        self.assertFalse(review.SELECTION.exists())


if __name__=="__main__":unittest.main()
