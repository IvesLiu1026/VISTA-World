"""Regression for observed Kit exit-0 masking of incomplete/failed experiments."""
import json
from pathlib import Path
import tempfile
import unittest

from isaac.run_bounded import inspect_result


class EvidenceRequired(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root/'data').mkdir()

    def write(self, value):
        (self.root/'data/results.json').write_text(json.dumps(value))

    def test_exit_zero_without_results_is_not_success(self):
        self.assertFalse(inspect_result(self.root)['checks_pass'])

    def test_nonempty_explicit_success_is_required(self):
        for value in ({}, {'checks':{}}, {'checks':[]}, {'checks':{'x':1}},
                      {'checks':{'x':'true'}}, {'checks':{'x':None}}, []):
            with self.subTest(value=value):
                self.write(value)
                self.assertFalse(inspect_result(self.root)['checks_pass'])

    def test_physical_failure_is_not_overridden_by_other_passes(self):
        self.write({'checks':{'sensor':True,'physical':False}})
        self.assertFalse(inspect_result(self.root)['checks_pass'])

    def test_python_error_takes_precedence_over_result_file(self):
        self.write({'checks':{'physical':True}})
        (self.root/'data/error.txt').write_text('later export failure')
        self.assertFalse(inspect_result(self.root)['checks_pass'])

    def test_partial_json_is_rejected(self):
        (self.root/'data/results.json').write_text('{"checks":')
        self.assertFalse(inspect_result(self.root)['checks_pass'])

    def test_complete_true_checks_accepted(self):
        self.write({'checks':{'sensor':True,'physical':True}})
        self.assertTrue(inspect_result(self.root)['checks_pass'])
