#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TIGER (Cas13d) on/off-target deep-learning predictor.

TIGER's artifact is a TensorFlow 2.11 SavedModel that the upstream code loads
with ``tf.keras.models.load_model('model')``.  On a server whose TensorFlow /
Keras has advanced (e.g. TensorFlow 2.2x with Keras 3) that call raises an
"unsupported format" error, because the directory is a classic
``tf.saved_model`` SavedModel rather than the current Keras SavedModel.

This module loads the artifact with the version-agnostic ``tf.saved_model.load``
and adapts the serving signature so the model can be called directly, while also
reproducing TIGER's two-channel one-hot encoding plus its calibration and
sigmoid score mapping.  It falls back to ``keras.layers.TFSMLayer`` when the
hosted loader path is not available.

Reference:
    Wessels et al., "Prediction of on-target and off-target activity of
    CRISPR-Cas13d guide RNAs using deep learning", Nature Biotechnology (2023),
    https://doi.org/10.1038/s41587-023-01830-8
"""

import os

import numpy as np

import scoring.model_registry as model_registry


# TIGER hyper-parameters (mirrored from the upstream ``tiger.py``).
GUIDE_LEN = 23
CONTEXT_5P = 3
CONTEXT_3P = 0
TARGET_LEN = CONTEXT_5P + GUIDE_LEN + CONTEXT_3P  # 26

NUCLEOTIDE_TOKENS = {"A": 0, "C": 1, "G": 2, "T": 3, "N": 255}
NUCLEOTIDE_COMPLEMENT = {"A": "T", "C": "G", "G": "C", "T": "A"}

# File names inside the model directory (all live under ``models/tiger``).
MODEL_DIRNAME = "tiger"
SCORING_FILE = "scoring_params.pkl"
CALIBRATION_FILE = "calibration_params.pkl"
SAVED_MODEL_RELPATH = "model"
SAVED_MODEL_MARKER = os.path.join(SAVED_MODEL_RELPATH, "saved_model.pb")


def _clean(seq):
    """Upper-case and normalise U to T (TIGER tokenizes U as T)."""
    return (seq or "").upper().replace("U", "T")


def _complement(seq):
    return "".join(NUCLEOTIDE_COMPLEMENT.get(base, "N") for base in _clean(seq))


def _reverse_complement(seq):
    return _complement(seq)[::-1]


def _tokenize(seq):
    return [NUCLEOTIDE_TOKENS.get(base, 255) for base in _clean(seq)]


def _one_hot(seq):
    """One-hot a tokenized sequence into a (len, 4) float32 matrix.

    ``N`` and any unknown base map to token 255, which one_hot(depth=4) renders
    as an all-zero vector (matching ``tf.one_hot`` in the upstream tokenizer).
    """
    tokens = _tokenize(seq)
    arr = np.zeros((len(tokens), 4), dtype=np.float32)
    for i, token in enumerate(tokens):
        if 0 <= token < 4:
            arr[i, token] = 1.0
    return arr


def _encode_pair(target_window, guide_protospacer):
    """Build one 208-column TIGER input vector from a target window + guide.

    ``target_window`` is the 26 nt target region (``CONTEXT_5P`` upstream
    context + the 23 nt protospacer, ``CONTEXT_3P`` downstream).  ``guide`` is
    the protospacer of the guide being evaluated.  TIGER's model channel is the
    complement of the protospacer (it never sees the biological crRNA directly),
    so the guide channel is ``CONTEXT_5P`` N-context bytes followed by
    ``complement(guide)``.  For on-target scoring both describe the same site;
    for off-target scoring ``target_window`` is the off-target site while
    ``guide`` stays the on-target protospacer.
    """
    target_window = _clean(target_window)
    if len(target_window) != TARGET_LEN:
        target_window = (target_window + "N" * TARGET_LEN)[:TARGET_LEN]
    guide_region = _complement(_clean(guide_protospacer))
    guide_vec = ("N" * CONTEXT_5P + guide_region + "N" * CONTEXT_3P)
    target_channel = _one_hot(target_window).reshape(-1)
    guide_channel = _one_hot(guide_vec).reshape(-1)
    return np.concatenate([target_channel, guide_channel]).astype(np.float32)


def build_target_window(guide, target_seq=None, spacer_start=None,
                        spacer_len=None):
    """Build the 26 nt TIGER target window with the real 3 nt upstream context.

    The toolkit stores ``guide`` as the forward protospacer on the target
    sequence (the sequence a crRNA is designed against), matching TIGER's
    ``target_seq[3:26]`` window.  When ``target_seq`` and ``spacer_start`` (the
    0-based protospacer start in ``target_seq``) are provided, the 3 nt upstream
    context is extracted from ``target_seq`` instead of being N-padded.

    Returns ``None`` when the guide cannot be confidently placed (no target
    sequence, unknown start, or a guide length that is not TIGER's 23 nt), so
    callers fall back to N-padding via :func:`build_input_vector`.
    """
    guide = _clean(guide)
    if len(guide) != GUIDE_LEN:
        return None
    if target_seq is None or spacer_start is None:
        return None
    target_seq = _clean(target_seq)
    start = int(spacer_start)
    spacer_len = int(spacer_len or GUIDE_LEN)
    if spacer_len != GUIDE_LEN:
        return None

    # The kit's guide is the forward protospacer; tolerate the reverse-complement
    # orientation as well in case a caller handed over the biological crRNA.
    window_region = target_seq[start:start + GUIDE_LEN]
    if window_region.upper() == guide.upper():
        upstream = target_seq[max(0, start - CONTEXT_5P):start]
        return (upstream + window_region + "N" * CONTEXT_3P)[:TARGET_LEN]
    if _reverse_complement(window_region).upper() == guide.upper():
        # crRNA orientation: guide is reverse-complement of the protospacer.
        # Upstream context is still the 3 nt 5' of the protospacer on the
        # transcript (i.e. immediately before the protospacer start).
        upstream = target_seq[max(0, start - CONTEXT_5P):start]
        return (upstream + window_region + "N" * CONTEXT_3P)[:TARGET_LEN]
    return None


def build_input_vector(guide, target_window=None):
    """Encode one on-target guide into the 208-column TIGER input vector.

    ``guide`` is the forward protospacer (23 nt) on the target transcript.  When
    ``target_window`` is omitted, the missing 3 nt upstream context are encoded
    as ``N`` (zeros), matching how TIGER pads transcript boundaries.  Pass a
    window from :func:`build_target_window` to use the real 3 nt upstream.
    """
    guide = _clean(guide)
    if len(guide) != GUIDE_LEN:
        raise ValueError("TIGER requires a %d nt guide, got %d"
                         % (GUIDE_LEN, len(guide)))
    if target_window is None:
        target_window = ("N" * CONTEXT_5P + guide + "N" * CONTEXT_3P)
    else:
        target_window = _clean(target_window)
    return _encode_pair(target_window, guide)


def _pick_default_dir():
    return os.path.join(model_registry.models_dir(), MODEL_DIRNAME)


class TigerPredictor:
    """Version-agnostic TIGER SavedModel predictor for Cas13d guides."""

    _instance = None

    def __init__(self, model_dir=None, scoring_path=None, calibration_path=None):
        self.model_dir = model_dir or _pick_default_dir()
        if not os.path.isdir(self.model_dir):
            raise FileNotFoundError(
                "TIGER model directory not found: %s (download it from the "
                "Models tab)" % self.model_dir)
        self.saved_model_dir = os.path.join(self.model_dir, SAVED_MODEL_RELPATH)
        if not os.path.isdir(self.saved_model_dir):
            # Allow a flat directory layout where the SavedModel files sit at
            # the top level (e.g. a manual copy).
            self.saved_model_dir = self.model_dir

        self.scoring_path = (scoring_path
                             or os.path.join(self.model_dir, SCORING_FILE))
        self.calibration_path = (calibration_path
                                 or os.path.join(self.model_dir, CALIBRATION_FILE))

        self._tf = None
        self._concrete = None
        self._tfsm_layer = None
        self._pd = None
        self.scoring_params = None
        self.calibration_params = None

        self._load_params()
        self._load_model()

    # ------------------------------------------------------------------ #
    # Class-level status helpers
    # ------------------------------------------------------------------ #
    @classmethod
    def default_model_dir(cls):
        return _pick_default_dir()

    @classmethod
    def has_files(cls):
        root = cls.default_model_dir()
        if not os.path.isdir(root):
            return False
        if not os.path.isfile(os.path.join(root, SAVED_MODEL_MARKER)):
            # Flat layout fallback.
            if not os.path.isfile(os.path.join(root, "saved_model.pb")):
                return False
        if not os.path.isfile(os.path.join(root, SCORING_FILE)):
            return False
        if not os.path.isfile(os.path.join(root, CALIBRATION_FILE)):
            return False
        return True

    @classmethod
    def status(cls, load=True):
        if not cls.has_files():
            return "not_downloaded"
        try:
            import tensorflow  # noqa: F401
        except ImportError:
            return "dependency_missing"
        try:
            if load:
                cls.get()
            return "ready"
        except Exception:
            return "load_error"

    @classmethod
    def available(cls):
        try:
            return cls.status(load=True) == "ready"
        except Exception:
            return False

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------ #
    # Loading
    # ------------------------------------------------------------------ #
    def _load_params(self):
        try:
            import pandas as pd
        except ImportError:
            raise RuntimeError("pandas is required to load TIGER scoring params")
        self._pd = pd
        self.scoring_params = pd.read_pickle(self.scoring_path)
        self.calibration_params = pd.read_pickle(self.calibration_path)

    def _load_model(self):
        try:
            import tensorflow as tf
        except ImportError:
            raise RuntimeError("tensorflow is required to run the TIGER model")
        self._tf = tf

        # Preferred path: hosted (Keras-independent) tf.saved_model load.  This
        # works even though the artifact carries keras_metadata.pb, which is
        # ignored by tf.saved_model.load.
        try:
            loaded = tf.saved_model.load(self.saved_model_dir)
            signatures = getattr(loaded, "signatures", None) or {}
            signature = signatures.get("serving_default")
            if signature is None and signatures:
                signature = next(iter(signatures.values()))
            if signature is not None:
                self._concrete = signature
                return
        except Exception:
            # Fall through to the Keras 3 layer wrapper below.
            self._concrete = None

        # Fallback: Keras 3's TFSMLayer wraps an arbitrary TF SavedModel as a
        # layer, which is the supported path when hosted loading is unavailable.
        try:
            from keras.layers import TFSMLayer
            self._tfsm_layer = TFSMLayer(
                self.saved_model_dir, call_endpoint="serving_default")
            return
        except Exception as exc:
            raise RuntimeError(
                "TIGER SavedModel is not loadable with tf.saved_model.load or "
                "keras.layers.TFSMLayer: %s" % exc)

    # ------------------------------------------------------------------ #
    # Inference
    # ------------------------------------------------------------------ #
    def _input_spec(self):
        """Return (name, dtype) of the single serving input, or (None, None)."""
        sig = self._concrete
        if sig is None:
            return None, None
        structured = getattr(sig, "structured_input_signature", None)
        if structured and len(structured) == 2 and structured[1]:
            name = next(iter(structured[1]))
            spec = structured[1][name]
            dtype = getattr(spec, "dtype", None)
            return name, dtype
        inputs = getattr(sig, "inputs", None)
        if inputs and len(inputs) == 1:
            return inputs[0].name, getattr(inputs[0], "dtype", None)
        return None, None

    def _run_serving(self, x, dtype):
        tf = self._tf
        if dtype is not None:
            try:
                x = tf.cast(x, dtype)
            except Exception:
                pass
        name, _ = self._input_spec()
        if name is not None:
            return self._concrete(**{name: x})
        return self._concrete(x)

    def _run(self, x):
        if self._concrete is not None:
            _, dtype = self._input_spec()
            result = self._run_serving(x, dtype)
        elif self._tfsm_layer is not None:
            result = self._tfsm_layer(tf_x(x, self._tf))
        else:
            raise RuntimeError("TIGER model was not loaded")
        return _to_flat_numpy(result)

    def _run_batch(self, x, batch_size=256):
        """Run the SavedModel over a pre-stacked (N, 208) float32 matrix."""
        outputs = []
        for start in range(0, len(x), batch_size):
            outputs.append(self._run(x[start:start + batch_size]))
        if not outputs:
            return np.array([], dtype=np.float32)
        return np.concatenate(outputs).astype(np.float32)

    def predict_lfc(self, guide_seqs, target_windows=None, batch_size=256):
        """Return the raw TIGER log-fold-change estimate for each on-target guide.

        Each ``guide`` is a 23 nt protospacer; ``target_windows`` (optional) are
        the corresponding 26 nt windows.  When omitted the 3 nt upstream context
        is N-padded.
        """
        guides = list(guide_seqs)
        windows = target_windows
        if windows is None:
            windows = [None] * len(guides)
        rows = []
        for guide, window in zip(guides, windows):
            try:
                rows.append(build_input_vector(guide, window))
            except ValueError:
                return None
        if not rows:
            return np.array([], dtype=np.float32)
        # The guide channel is taken from each row's protospacer.  For on-target
        # scoring the window's protospacer equals the guide, so build_input_vector
        # already used _encode_pair(window, guide); checking again is unnecessary.
        return self._run_batch(np.stack(rows).astype(np.float32), batch_size)

    def predict_lfc_for_targets(self, guide, target_windows, batch_size=256):
        """Score one (on-target) guide against a battery of target windows.

        Used for off-target scoring: the on-target guide stays in the guide
        channel while each off-target appears only in the target channel.
        """
        guide = _clean(guide)
        if len(guide) != GUIDE_LEN:
            return None
        if not target_windows:
            return np.array([], dtype=np.float32)
        rows = [_encode_pair(tw, guide) for tw in target_windows]
        return self._run_batch(np.stack(rows).astype(np.float32), batch_size)

    def _calibrate(self, lfc, num_mismatches):
        params = self.calibration_params
        try:
            indexed = params.set_index("num_mismatches")
        except Exception:
            indexed = params
        if np.isscalar(num_mismatches):
            try:
                slope = indexed.loc[int(num_mismatches), "slope"]
                correction = float(np.asarray(slope).reshape(-1)[0])
            except Exception:
                correction = 1.0
            return correction * np.asarray(lfc, dtype=np.float64)
        mm = np.asarray(num_mismatches, dtype=int)
        try:
            rows = indexed.loc[mm, "slope"].to_numpy()
            correction = np.asarray(rows, dtype=np.float64).reshape(-1)
            if len(correction) == 1:
                correction = np.repeat(correction, len(mm))
        except Exception:
            correction = np.ones(len(mm), dtype=np.float64)
        return correction * np.asarray(lfc, dtype=np.float64)

    def _score(self, calibrated):
        params = self.scoring_params
        row = params.iloc[0]
        a = float(row["a"])
        b = float(row["b"])
        x = np.clip(a * np.asarray(calibrated, dtype=np.float64) + b, -60.0, 60.0)
        # 1 - sigmoid(a * lfc + b), matching TIGER's UNIT_INTERVAL_MAP.
        return (1.0 - 1.0 / (1.0 + np.exp(x))).astype(np.float32)

    def score_guides(self, guide_seqs, target_windows=None, num_mismatches=0,
                     batch_size=256):
        """Return a [0, 1] TIGER guide score for each input guide."""
        lfc = self.predict_lfc(guide_seqs, target_windows, batch_size=batch_size)
        if lfc is None:
            return None
        calibrated = self._calibrate(lfc, num_mismatches)
        return self._score(calibrated)

    def score_guide(self, guide_seq, target_window=None):
        scores = self.score_guides([guide_seq], [target_window])
        if scores is None or len(scores) == 0:
            return None
        return float(scores[0])


def tf_x(x, tf):
    return tf.convert_to_tensor(x, dtype=tf.float32)


def _to_flat_numpy(result):
    """Convert a serving output (dict or tensor) to a flat float32 array."""
    if isinstance(result, dict):
        values = []
        for value in result.values():
            if hasattr(value, "shape"):
                values.append(value)
        if not values:
            raise RuntimeError("TIGER serving output has no tensor value")
        if len(values) == 1:
            tensor = values[0]
        else:
            def _size(t):
                shape = getattr(t.shape, "as_list", lambda: None)()
                if shape is None:
                    return 0
                size = 1
                for dim in shape:
                    if dim is None:
                        size = 0
                        break
                    size *= int(dim)
                return size
            # Prefer the smallest non-empty tensor, typically the scalar logit.
            tensor = min(values, key=lambda t: _size(t) or 10 ** 9)
    else:
        tensor = result
    arr = tensor.numpy()
    if arr.ndim > 1:
        arr = arr[:, 0]
    return arr.reshape(-1).astype(np.float32)


def tiger_status(load=True):
    return TigerPredictor.status(load=load)


def score_guide(guide_seq, target_window=None):
    """Convenience single-guide scorer returning a [0, 1] score or None."""
    if not TigerPredictor.available():
        return None
    guide_seq = _clean(guide_seq)
    if len(guide_seq) != GUIDE_LEN:
        return None
    try:
        return TigerPredictor.get().score_guide(guide_seq, target_window)
    except Exception:
        return None


def score_batch(guide_seqs, target_windows=None, num_mismatches=0):
    """Convenience batch scorer returning a numpy array of [0, 1] scores."""
    if not TigerPredictor.available():
        return None
    try:
        return TigerPredictor.get().score_guides(
            guide_seqs, target_windows, num_mismatches=num_mismatches)
    except Exception:
        return None


def cas13_off_target_specificity(guide, off_pairs, assume_one_primary=True):
    """Aggregate TIGER off-target activity like GuideScan2's CFD sum.

    ``off_pairs`` is ``[(off_spacer, pam), ...]``.  Every off-spacer is scored
    with TIGER and the activity values are summed (subtracting one perfect hit
    when requested), then mapped to ``1 / (1 + sum)`` like the other models.
    Returns ``None`` when TIGER is unavailable or the guide length is not 23.
    """
    guide_seq = _clean(guide)
    if not TigerPredictor.available():
        return None
    if len(guide_seq) != GUIDE_LEN:
        return None
    if not off_pairs:
        return 1.0
    target_windows = []
    num_mismatches = []
    for off_spacer, _pam in off_pairs:
        off = _clean(off_spacer)
        # TIGER's off-target input uses the off-target site in the target
        # channel while the on-target guide stays in the guide channel.
        target_windows.append("N" * CONTEXT_5P + off + "N" * CONTEXT_3P)
        n = min(len(guide_seq), len(off))
        num_mismatches.append(sum(1 for a, b in zip(guide_seq[:n], off[:n])
                                  if a != b))
    predictor = TigerPredictor.get()
    lfc = predictor.predict_lfc_for_targets(guide_seq, target_windows)
    if lfc is None:
        return None
    calibrated = predictor._calibrate(lfc, num_mismatches)
    scores = predictor._score(calibrated)
    total = 0.0
    has_primary = False
    for raw, mm in zip(scores, num_mismatches):
        value = float(raw)
        # TIGER scores are monotonically increasing with predicted activity, so
        # cap at the [0, 1] range.  TIGER scores rarely reach 0.999999, so the
        # primary (0-mismatch) target is detected by mismatch count instead.
        activity = max(0.0, min(1.0, value))
        total += activity
        if int(mm) == 0:
            has_primary = True
    if assume_one_primary and has_primary:
        total = max(0.0, total - 1.0)
    return 1.0 / (1.0 + total)
