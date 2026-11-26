import contextlib
import io
from pathlib import Path
import tempfile
import unittest

from cusip_validation_claim_audit.audit import audit, claims, evidence, main
from cusip_validation_claim_audit.phrases import CUSIPVALIDATION, NOCUSIPVALIDATION, GENERIC_NAMES


class AuditTests(unittest.TestCase):
    def test_phrases(self):
        self.assertEqual((len(CUSIPVALIDATION), len(NOCUSIPVALIDATION), len(GENERIC_NAMES)), (50, 24, 24))
        for phrase in CUSIPVALIDATION:
            with self.subTest(phrase=phrase):
                self.assertEqual(claims(phrase), (True, False))
        for phrase in NOCUSIPVALIDATION:
            with self.subTest(phrase=phrase):
                self.assertEqual(claims(phrase), (False, True))
        self.assertEqual(claims('```\nvalidate cusip\n```\n~~~\nno cusip validation\n~~~'), (False, False))
        self.assertEqual(claims("doesn't validate-cusip"), (False, True))
        self.assertEqual(claims('`validate cusip`'), (True, False))

    def test_library_routes(self):
        for method in ('validate', 'is_valid'):
            for source in ('import stdnum.cusip\nstdnum.cusip.%s(x)', 'import stdnum.cusip as s\ns.%s(x)', 'import stdnum\nstdnum.cusip.%s(x)', 'from stdnum import cusip as s\ns.%s(x)', 'from stdnum.cusip import %s as f\nf(x)'):
                with self.subTest(source=source, method=method):
                    self.assertTrue(evidence(source % method))
        for source in ('import validators\nvalidators.cusip(x)', 'import validators as v\nv.cusip(x)', 'from validators import cusip\ncusip(x)', 'from validators import cusip as c\nc(x)', 'from validators.finance import cusip\ncusip(x)'):
            with self.subTest(source=source):
                self.assertTrue(evidence(source))

    def test_generic_routes(self):
        for name in GENERIC_NAMES:
            with self.subTest(name=name):
                self.assertTrue(evidence('obj.%s(x)' % name))
                self.assertTrue(evidence('from lib import %s as f\nf(x)' % name))
                self.assertFalse(evidence('%s(x)' % name))
                self.assertFalse(evidence('def %s(x): pass\nobj.%s(x)' % (name, name)))
        self.assertTrue(evidence('result = thing()\nresult.validate_cusip(x)'))

    def test_not_evidence(self):
        cases = ['import validators', 'import stdnum.cusip', 'cusip(x)', 'validate(x)', 'is_valid(x)', 'compact(x)', 'calc_check_digit(x)', 'to_isin(x)', 'validate_cusip(x)', 'obj.cusip(x)', 'obj.validate(x)', 'obj.is_valid(x)', 'obj.compact(x)', 'obj.calc_check_digit(x)', 'obj.to_isin(x)', 'import stdnum.cusip\nstdnum.cusip.compact(x)', 'import stdnum.cusip\nstdnum.cusip.calc_check_digit(x)', 'import stdnum.cusip\nstdnum.cusip.to_isin(x)', 'import stdnum.isin\nstdnum.isin.validate(x)', 'import stdnum.isin\nstdnum.isin.is_valid(x)', 'import stdnum.isin\nstdnum.isin.from_natid(x)', 'import validators\nvalidators.isin(x)', 'obj.validate_sedol(x)', 'obj.validate_figi(x)', 'obj.validate_isni(x)', 'import re\nre.match("x", x)', 'import re\nre.search("x", x)', 'import re\nre.fullmatch("x", x)', 'len(x) == 9', 'x[4] == " "', 'all(c in "ABC" for c in x)', 'obj.lookup_cusip(x)', 'obj.generate_cusip()', '"validate cusip"', '# cusip validation', 'validate_cusip', 'def broken(', 'import subprocess\nsubprocess.run(["checker", x])', 'import stdnum.cusip as s\ns = x\ns.validate(x)', 'from stdnum.cusip import validate\ndef validate(x): pass\nvalidate(x)', 'import validators as v\nwith thing() as v: pass\nv.cusip(x)', 'from validators import cusip\ncusip: object = x\ncusip(x)']
        for source in cases:
            with self.subTest(source=source):
                self.assertFalse(evidence(source))

    def test_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'README.md').write_text('validate cusip')
            self.assertEqual(audit(root)[0]['severity'], 'HIGH')
            (root / 'tests').mkdir()
            (root / 'tests/test_x.py').write_text('import validators\nvalidators.cusip(x)')
            self.assertEqual(audit(root)[0]['severity'], 'MEDIUM')
            (root / 'app.py').write_text('import stdnum.cusip\nstdnum.cusip.is_valid(x)')
            self.assertEqual(audit(root), [])
            (root / 'README.md').write_text('no cusip validation')
            self.assertEqual(audit(root)[0]['id'], 'documented-no-cusip-validation-claim-false')
            self.assertEqual(audit(root, ['app.py']), [])
            self.assertEqual(audit(root, ['app.py', 'tests']), [])
        project = Path(__file__).resolve().parents[1]
        self.assertEqual(audit(project), [])
        readme = (project / 'README.md').read_text()
        self.assertEqual(claims(readme), (False, False))
        fenced = False
        for line in readme.splitlines():
            if line.startswith('```'):
                fenced = not fenced
            elif not fenced:
                self.assertNotIn('cusip-validation-claim-audit', line)
                self.assertNotIn('documented-cusip-validation-claim-false', line)
                self.assertNotIn('documented-no-cusip-validation-claim-false', line)
        self.assertNotIn('the phrase', readme)
        self.assertNotIn('a tool that', readme)

    def test_cli(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['audit', tmp, '--json']), 0)
            self.assertEqual(main(['audit', tmp, '--fail-on', 'medium']), 0)
            self.assertEqual(main(['audit', tmp + '/missing']), 1)
            Path(tmp, 'README.md').write_text('validate cusip')
            self.assertEqual(main(['audit', tmp]), 2)
