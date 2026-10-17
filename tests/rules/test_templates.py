from dataclasses import replace
import unittest
from rules.engine import TEMPLATES, evaluate_template
from rules.types import RuleInputs, Truth


def complete(**overrides):
    return replace(RuleInputs(antecedent=Truth.TRUE,condition=Truth.FALSE,exception=Truth.FALSE,
                             interval_complete=True,visibility_complete=True,recognizer_validated=True,
                             stage_ended=True,alternatives_checked=True,relations_known=True),**overrides)


class TemplateTests(unittest.TestCase):
    def test_positive_hard_negative_truncated_occlusion_exception_for_each(self):
        for template in TEMPLATES:
            with self.subTest(template=template):
                positive=complete(condition=Truth.TRUE if template=='presence' else Truth.FALSE)
                negative=complete(condition=Truth.FALSE if template=='presence' else Truth.TRUE)
                self.assertEqual(evaluate_template(template,positive),'triggered')
                self.assertEqual(evaluate_template(template,negative),'not_triggered')
                truncated=replace(positive,interval_complete=False,stage_ended=False)
                self.assertEqual(evaluate_template(template,truncated),'triggered' if template=='presence' else 'unknown')
                self.assertEqual(evaluate_template(template,replace(positive,visibility_complete=False)),'unknown')
                self.assertEqual(evaluate_template(template,replace(positive,exception=Truth.TRUE)),'not_triggered')
                for field in ('recognizer_validated','relations_known'):
                    self.assertEqual(evaluate_template(template,replace(positive,**{field:False})),'unknown')
                self.assertEqual(evaluate_template(template,replace(positive,exception=Truth.UNKNOWN)),'unknown')

    def test_every_absence_gate_is_required(self):
        for template in TEMPLATES-{'presence'}:
            for field in ('interval_complete','visibility_complete','recognizer_validated','stage_ended','alternatives_checked','relations_known'):
                with self.subTest(template=template,field=field):
                    self.assertEqual(evaluate_template(template,replace(complete(),**{field:False})),'unknown')

    def test_missing_events_are_unknown_not_negative(self):
        for template in TEMPLATES:
            self.assertEqual(evaluate_template(template,RuleInputs()),'unknown')


if __name__=='__main__': unittest.main()
