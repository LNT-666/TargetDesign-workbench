#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Real-model integration smoke test for TIGER (skipped when unavailable).

This test actually loads the TIGER SavedModel and runs inference, so it only
executes on a host that has TensorFlow and the downloaded model (the server
venv).  On a desktop without TensorFlow it is skipped, and the encoding /
fallback behaviour is covered by ``test_tiger_model`` instead.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

import numpy as np  # noqa: E402

import scoring.tiger_model as tiger_model  # noqa: E402


# First 50 nt of EIF3B-003 CDS, the built-in example used by upstream tiger.py.
TRANSCRIPT = "ATGCAGGACGCGGAGAACGTGGCGGTGCCCGAGGCGGCCGAGGAGCGCGC"


@unittest.skipUnless(
    tiger_model.TigerPredictor.available(),
    "TIGER model or TensorFlow runtime not available")
class TigerInferenceTests(unittest.TestCase):
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
        guide_len = tiger_model.GUIDE_LEN  # 23
        windows = [
            transcript[i:i + tiger_model.TARGET_LEN]
            for i in range(len(transcript) - tiger_model.TARGET_LEN + 1)
        ]
        # The kit stores the forward protospacer (target region), which is
        # TIGER's ``target_seq[3:26]`` window.
        guides = [w[tiger_model.CONTEXT_5P:tiger_model.TARGET_LEN] for w in windows]
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
        self.assertIsNone(tiger_model.build_target_window(protospacer, None, None))
        # An out-of-range start must not crash and must use N-padding.
        self.assertIsNone(tiger_model.build_target_window(
            protospacer, transcript, 999))


if __name__ == "__main__":
    unittest.main()
