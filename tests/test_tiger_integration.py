#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Real-model integration smoke test for TIGER (skipped when unavailable).

This test actually loads the TIGER SavedModel and runs inference, so it only
executes on a host that has TensorFlow and the downloaded model (the server
venv).  On a desktop without TensorFlow it is skipped, and the encoding /
fallback behaviour is covered by ``test_tiger_model`` instead.  The real model
tests run in a worker subprocess so model loading cannot affect the parent
test process.
"""

import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

import numpy as np  # noqa: E402

import scoring.tiger_model as tiger_model  # noqa: E402


# First 50 nt of EIF3B-003 CDS, the built-in example used by upstream tiger.py.
TRANSCRIPT = "ATGCAGGACGCGGAGAACGTGGCGGTGCCCGAGGCGGCCGAGGAGCGCGC"
WORKER_FLAG = "--worker"
WORKER_TIMEOUT_SECONDS = 300
IS_WORKER = WORKER_FLAG in sys.argv


if IS_WORKER:
    class TigerInferenceTests(unittest.TestCase):
        @classmethod
        def setUpClass(cls):
            if not tiger_model.TigerPredictor.available():
                raise unittest.SkipTest(
                    "TIGER model or TensorFlow runtime not available")

        def test_model_readiness(self):
            import scoring.model_registry as mr
            self.assertEqual(mr.get_model_status("tiger"), "ready")
            self.assertTrue(tiger_model.TigerPredictor.available())

        def test_registry_download_target_is_complete(self):
            import scoring.model_registry as mr
            info = mr.MODELS["tiger"]
            target = mr.get_model_path("tiger")
            self.assertTrue(mr._dir_files_present(info, target))

        def test_minimal_transcript_scores_in_unit_interval(self):
            transcript = TRANSCRIPT.upper().replace("U", "T")
            windows = [
                transcript[i:i + tiger_model.TARGET_LEN]
                for i in range(len(transcript) - tiger_model.TARGET_LEN + 1)
            ]
            # The kit stores the forward protospacer (target region), which is
            # TIGER's ``target_seq[3:26]`` window.
            guides = [w[tiger_model.CONTEXT_5P:tiger_model.TARGET_LEN]
                      for w in windows]
            scores = tiger_model.TigerPredictor.get().score_guides(guides, windows)
            self.assertIsNotNone(scores)
            self.assertEqual(len(scores), len(guides))
            self.assertTrue(np.all(np.isfinite(scores)))
            self.assertGreaterEqual(float(scores.min()), 0.0)
            self.assertLessEqual(float(scores.max()), 1.0)

        def test_single_guide_reproduces_batch(self):
            guide = TRANSCRIPT[3:26]  # forward protospacer
            batch = tiger_model.TigerPredictor.get().score_guides([guide])
            single = tiger_model.score_guide(guide)
            self.assertIsNotNone(single)
            self.assertAlmostEqual(float(batch[0]), single, places=6)

        def test_real_upstream_context_extraction(self):
            transcript = TRANSCRIPT.upper().replace("U", "T")
            protospacer = transcript[3:3 + tiger_model.GUIDE_LEN]
            window = tiger_model.build_target_window(
                protospacer, transcript, 3)
            self.assertEqual(window, transcript[0:26])
            # N-padding fallback when there is no target sequence.
            self.assertIsNone(
                tiger_model.build_target_window(protospacer, None, None))
            # An out-of-range start must not crash and must use N-padding.
            self.assertIsNone(tiger_model.build_target_window(
                protospacer, transcript, 999))
else:
    class TigerInferenceProcessTests(unittest.TestCase):
        def test_real_model_tests_in_isolated_process(self):
            self.assertIsNone(
                tiger_model.TigerPredictor._instance,
                "TIGER model was loaded before the worker subprocess")

            worker = [sys.executable, os.path.abspath(__file__), WORKER_FLAG]
            env = os.environ.copy()
            env["PYTHONUTF8"] = "1"
            try:
                completed = subprocess.run(
                    worker,
                    cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=WORKER_TIMEOUT_SECONDS,
                    env=env,
                )
            except subprocess.TimeoutExpired as exc:
                self.fail(
                    "TIGER model worker timed out after "
                    f"{WORKER_TIMEOUT_SECONDS} seconds\n"
                    f"stdout:\n{exc.stdout or ''}\n"
                    f"stderr:\n{exc.stderr or ''}")
            except OSError as exc:
                self.fail(f"TIGER model worker could not start: {exc}")

            worker_output = (
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}")
            self.assertIsNone(
                tiger_model.TigerPredictor._instance,
                "The worker subprocess changed the parent TIGER model instance")
            with self.subTest(process="TIGER model worker"):
                self.assertEqual(
                    completed.returncode, 0,
                    f"TIGER model worker failed\n{worker_output}")

            if "skipped" in completed.stderr:
                self.skipTest(
                    "TIGER model worker skipped: model or TensorFlow unavailable")


if __name__ == "__main__":
    if IS_WORKER:
        worker_suite = unittest.defaultTestLoader.loadTestsFromTestCase(
            TigerInferenceTests)
        worker_result = unittest.TextTestRunner(verbosity=2).run(worker_suite)
        sys.exit(0 if worker_result.wasSuccessful() else 1)
    unittest.main()
