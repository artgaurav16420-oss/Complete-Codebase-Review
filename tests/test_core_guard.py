"""Guard: the default suite must exercise the ccr core."""

import unittest


class TestCoreGuard(unittest.TestCase):
    def test_ccr_core_is_importable(self):
        from ccr import findings, pipeline, report
        self.assertTrue(callable(pipeline.synthesize))
        self.assertTrue(callable(findings.aggregate))
        self.assertTrue(callable(report.render_markdown))


if __name__ == "__main__":
    unittest.main()
