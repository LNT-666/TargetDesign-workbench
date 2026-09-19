#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Optional local deep-learning predictors for guide off-target scoring.

CRISPR-M is loaded directly from its Keras HDF5 weights.  The forward pass is
implemented with NumPy so the model does not require TensorFlow on the user's
machine.  DeepCRISPR uses a TensorFlow 1.x checkpoint; this module exposes its
runtime status and falls back gracefully when that runtime is unavailable.
"""

import math
import os

import numpy as np

import scoring.model_registry as model_registry
from scoring.tiger_model import TigerPredictor as _TigerPredictor
from scoring.deepcrispr_forward import DeepCrisprForward
from scoring.deepcrispr_forward import make_inputs as deepcrispr_make_inputs
from scoring.deepcpf1_forward import DeepCpf1Forward


_PAD = "_"
_TLEN = 24
_SPACER = 20

_BASE_PAIR_V3 = {
    "AA": 0, "TT": 1, "GG": 2, "CC": 3,
    "AT": 4, "AG": 5, "AC": 6, "TG": 7, "TC": 8, "GC": 9,
    "TA": 10, "GA": 11, "CA": 12, "GT": 13, "CT": 14, "CG": 15,
    "A_": 16, "T_": 17, "G_": 18, "C_": 19,
    "_A": 20, "_T": 21, "_G": 22, "_C": 23,
    "__": 24,
}
_BASE_V3 = {"A": 25, "T": 26, "G": 27, "C": 28, "_": 29}


def _clean(seq):
    return (seq or "").upper().replace("U", "T").replace("-", "_")


def _pad24(seq):
    seq = _clean(seq)
    if len(seq) < _TLEN:
        seq = _PAD * (_TLEN - len(seq)) + seq
    return seq[:_TLEN]


def make_24mer(guide, pam=None):
    """Build the 20 nt spacer + 3 nt PAM window expected by CRISPR-M."""
    guide = _clean(guide)
    pam = _clean(pam or "")
    if pam and guide.endswith(pam):
        guide = guide[:-len(pam)]
    if len(pam) < 3:
        pam = "N" + pam
    if len(pam) > 3:
        pam = pam[-3:]
    spacer = guide[-_SPACER:] if len(guide) >= _SPACER else guide
    return _pad24(spacer + pam)


def encode_base_pair(on_seq, off_seq):
    """Encode one 24-mer guide/off-target pair as the vocabulary integers."""
    on_seq = _pad24(on_seq)
    off_seq = _pad24(off_seq)
    out = np.zeros((_TLEN,), dtype=np.int32)
    for i in range(_TLEN):
        key = on_seq[i] + off_seq[i]
        out[i] = _BASE_PAIR_V3.get(key, _BASE_PAIR_V3["__"])
    return out


def encode_single_base(seq):
    seq = _pad24(seq)
    return np.array([_BASE_V3.get(base, _BASE_V3[_PAD]) for base in seq],
                    dtype=np.int32)


def _softmax(x, axis=-1):
    x = x - np.max(x, axis=axis, keepdims=True)
    exp = np.exp(x)
    return exp / np.sum(exp, axis=axis, keepdims=True)


def _conv2d_1d(x, kernel, bias):
    """Conv2D with kernel shape [1, kw, in_ch, out_ch]."""
    n, h, w, in_ch = x.shape
    kw = kernel.shape[1]
    out_ch = kernel.shape[3]
    k = kernel[0]
    out = np.zeros((n, h, w - kw + 1, out_ch), dtype=np.float32)
    for pos in range(out.shape[2]):
        window = x[:, :, pos:pos + kw, :]
        out[:, :, pos, :] = np.einsum("nhkc,kco->nho", window, k,
                                      optimize=True) + bias
    return out


def _batch_norm(x, gamma, beta, moving_mean, moving_variance, epsilon=0.001):
    scale = gamma / np.sqrt(moving_variance + epsilon)
    return (x - moving_mean) * scale + beta


def _multi_head_attention(x, wq, bq, wk, bk, wv, bv, wo, bo, key_dim=6):
    q = np.einsum("btd,dhk->bthk", x, wq, optimize=True) + bq
    k = np.einsum("btd,dhk->bthk", x, wk, optimize=True) + bk
    v = np.einsum("btd,dhk->bthk", x, wv, optimize=True) + bv
    logits = np.einsum("bthk,bshk->bhts", q, k, optimize=True)
    logits = logits / math.sqrt(key_dim)
    weights = _softmax(logits, axis=-1)
    context = np.einsum("bhts,bshk->bthk", weights, v, optimize=True)
    return np.einsum("bthk,hkd->btd", context, wo, optimize=True) + bo


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -40.0, 40.0)))


def _lstm_forward(x, kernel, recurrent_kernel, bias, units,
                  activation=np.tanh, recurrent_activation=_sigmoid):
    n, steps, _ = x.shape
    h = np.zeros((n, units), dtype=np.float32)
    c = np.zeros((n, units), dtype=np.float32)
    outputs = []
    for t in range(steps):
        xt = x[:, t, :]
        gates = xt @ kernel + h @ recurrent_kernel + bias
        i = recurrent_activation(gates[:, :units])
        f = recurrent_activation(gates[:, units:2 * units])
        g = activation(gates[:, 2 * units:3 * units])
        o = recurrent_activation(gates[:, 3 * units:])
        c = f * c + i * g
        h = o * activation(c)
        outputs.append(h)
    return np.stack(outputs, axis=1)


class CrisprMPredictor:
    """NumPy forward pass for the local CRISPR-M HDF5 model."""

    _instance = None

    def __init__(self, h5_path=None):
        self.h5_path = h5_path or model_registry.get_model_path("crispr_m")
        if not self.h5_path or not os.path.isfile(self.h5_path):
            raise FileNotFoundError("CRISPR-M model file not found")
        try:
            import h5py
        except ImportError:
            raise RuntimeError("h5py is required to load the CRISPR-M model")
        self.weights = {}
        with h5py.File(self.h5_path, "r") as handle:
            base = "model_weights/"
            def collect(name, obj):
                if isinstance(obj, h5py.Dataset):
                    self.weights[name] = obj[()]
            handle[base].visititems(collect)
        self.embedding = self.weights["embedding/embedding/embeddings:0"]
        self._load_attention()
        self._load_convs()
        self._load_lstm()
        self._load_head()

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _w(self, name):
        key = name + ":0"
        if key not in self.weights:
            raise KeyError("Missing CRISPR-M weight: %s" % key)
        return self.weights[key]

    def _load_attention(self):
        self.attention = []
        for prefix in ("multi_head_attention/multi_head_attention",
                       "multi_head_attention_1/multi_head_attention_1",
                       "multi_head_attention_2/multi_head_attention_2"):
            self.attention.append({
                "wq": self._w(prefix + "/query/kernel"),
                "bq": self._w(prefix + "/query/bias"),
                "wk": self._w(prefix + "/key/kernel"),
                "bk": self._w(prefix + "/key/bias"),
                "wv": self._w(prefix + "/value/kernel"),
                "bv": self._w(prefix + "/value/bias"),
                "wo": self._w(prefix + "/attention_output/kernel"),
                "bo": self._w(prefix + "/attention_output/bias"),
            })

    def _load_convs(self):
        self.convs = []
        for prefix in ("conv2d/conv2d", "conv2d_1/conv2d_1",
                       "conv2d_2/conv2d_2", "conv2d_3/conv2d_3",
                       "conv2d_4/conv2d_4"):
            self.convs.append((self._w(prefix + "/kernel"),
                               self._w(prefix + "/bias")))
        self.bns = []
        for prefix in ("batch_normalization", "batch_normalization_1",
                       "batch_normalization_2", "batch_normalization_3",
                       "batch_normalization_4", "batch_normalization_5",
                       "batch_normalization_6"):
            inner = prefix + "/" + prefix
            self.bns.append({
                "gamma": self._w(inner + "/gamma"),
                "beta": self._w(inner + "/beta"),
                "mean": self._w(inner + "/moving_mean"),
                "var": self._w(inner + "/moving_variance"),
            })

    def _load_lstm(self):
        self.lstm = []
        paths = [
            ("bidirectional/bidirectional/forward_lstm/lstm_cell_1",
             "bidirectional/bidirectional/backward_lstm/lstm_cell_2"),
            ("bidirectional_1/bidirectional_1/forward_lstm_1/lstm_cell_4",
             "bidirectional_1/bidirectional_1/backward_lstm_1/lstm_cell_5"),
            ("bidirectional_2/bidirectional_2/forward_lstm_2/lstm_cell_7",
             "bidirectional_2/bidirectional_2/backward_lstm_2/lstm_cell_8"),
            ("bidirectional_3/bidirectional_3/forward_lstm_3/lstm_cell_10",
             "bidirectional_3/bidirectional_3/backward_lstm_3/lstm_cell_11"),
        ]
        for fwd, bwd in paths:
            self.lstm.append({
                "fwd": (self._w(fwd + "/kernel"),
                        self._w(fwd + "/recurrent_kernel"),
                        self._w(fwd + "/bias")),
                "bwd": (self._w(bwd + "/kernel"),
                        self._w(bwd + "/recurrent_kernel"),
                        self._w(bwd + "/bias")),
            })

    def _load_head(self):
        self.dense1 = (self._w("dense/dense/kernel"),
                       self._w("dense/dense/bias"))
        self.dense2 = (self._w("dense_1/dense_1/kernel"),
                       self._w("dense_1/dense_1/bias"))
        self.output = (self._w("output/output/kernel"),
                       self._w("output/output/bias"))

    def _branch(self, attention_out, convs, bns, lstm, two_convs=True):
        x = attention_out.reshape((-1, 24, 7, 1))
        x = _conv2d_1d(x, convs[0][0], convs[0][1])
        x = _batch_norm(x, bns[0]["gamma"], bns[0]["beta"],
                        bns[0]["mean"], bns[0]["var"])
        if two_convs:
            x = _conv2d_1d(x, convs[1][0], convs[1][1])
            x = _batch_norm(x, bns[1]["gamma"], bns[1]["beta"],
                            bns[1]["mean"], bns[1]["var"])
        x = x.reshape((-1, 24, x.shape[-1]))
        kernel, recurrent_kernel, bias = lstm["fwd"]
        fwd = _lstm_forward(x, kernel, recurrent_kernel, bias, 32)
        kernel, recurrent_kernel, bias = lstm["bwd"]
        bwd = _lstm_forward(x[:, ::-1, :], kernel, recurrent_kernel, bias, 32)
        bwd = bwd[:, ::-1, :]
        return np.concatenate([fwd, bwd], axis=-1)

    def forward(self, x1, x2, x3):
        """x1/x2/x3 are integer arrays shaped (batch, 24)."""
        if x1.dtype != np.int32:
            x1 = x1.astype(np.int32)
        if x2.dtype != np.int32:
            x2 = x2.astype(np.int32)
        if x3.dtype != np.int32:
            x3 = x3.astype(np.int32)
        embedded = self.embedding[x1], self.embedding[x2], self.embedding[x3]
        positions = _positional_encoding(24, 7)
        embedded = [e + positions for e in embedded]

        att0 = _multi_head_attention(embedded[0], **self.attention[0])
        att1 = _multi_head_attention(embedded[1], **self.attention[1])
        att2 = _multi_head_attention(embedded[2], **self.attention[2])

        branch1 = self._branch(att0, [self.convs[0], self.convs[1]],
                               [self.bns[0], self.bns[1]], self.lstm[0],
                               two_convs=True)
        branch2 = self._branch(att0, [self.convs[2]], [self.bns[2]],
                               self.lstm[1], two_convs=False)
        branch3 = self._branch(att1, [self.convs[3]], [self.bns[3]],
                               self.lstm[2], two_convs=False)
        branch4 = self._branch(att2, [self.convs[4]], [self.bns[4]],
                               self.lstm[3], two_convs=False)
        features = np.concatenate([branch1, branch2, branch3, branch4], axis=-1)
        features = features.reshape((features.shape[0], -1))

        hidden = features @ self.dense1[0] + self.dense1[1]
        hidden = _batch_norm(hidden, self.bns[5]["gamma"], self.bns[5]["beta"],
                             self.bns[5]["mean"], self.bns[5]["var"])
        hidden = hidden @ self.dense2[0] + self.dense2[1]
        hidden = _batch_norm(hidden, self.bns[6]["gamma"], self.bns[6]["beta"],
                             self.bns[6]["mean"], self.bns[6]["var"])
        logits = hidden @ self.output[0] + self.output[1]
        return _sigmoid(logits.reshape(-1))

    def predict(self, guide, off_spacer, pam=None):
        on24 = make_24mer(guide, pam)
        off24 = make_24mer(off_spacer, pam)
        x1 = encode_base_pair(on24, off24)[None, :]
        x2 = encode_single_base(on24)[None, :]
        x3 = encode_single_base(off24)[None, :]
        return float(self.forward(x1, x2, x3)[0])

    def predict_pairs(self, guide, off_spacers, pam=None):
        """Score one guide against multiple off-targets in one forward pass."""
        if not off_spacers:
            return []
        on24 = make_24mer(guide, pam)
        x1, x2, x3 = [], [], []
        for off_spacer in off_spacers:
            off24 = make_24mer(off_spacer, pam)
            x1.append(encode_base_pair(on24, off24))
            x2.append(encode_single_base(on24))
            x3.append(encode_single_base(off24))
        return self.forward(
            np.stack(x1), np.stack(x2), np.stack(x3)).tolist()


def _positional_encoding(max_steps, max_dims):
    dims = max_dims + 1 if max_dims % 2 else max_dims
    pe = np.zeros((1, max_steps, dims), dtype=np.float32)
    pos = np.arange(max_steps, dtype=np.float32).reshape(-1, 1)
    half = dims // 2
    div = np.power(10000.0, 2.0 * np.arange(half, dtype=np.float32) / dims)
    pe[0, :, 0::2] = np.sin(pos / div)
    pe[0, :, 1::2] = np.cos(pos / div)
    return pe[:, :, :max_dims]


class DeepCrisprPredictor:
    """NumPy forward pass for the converted DeepCRISPR checkpoint."""

    _instance = None

    @classmethod
    def status(cls, load=True):
        portable = os.path.join(model_registry.models_dir(),
                                "deepcrispr_offtar_pt_cnn_reg.portable.npz")
        if not os.path.isfile(portable):
            source = model_registry.get_model_path("deepcrispr")
            if not source or not os.path.isfile(source):
                return "not_downloaded"
            return "needs_conversion"
        try:
            if load and cls._instance is None:
                cls._instance = DeepCrisprForward(portable)
            return "ready"
        except Exception:
            return "load_error"

    @classmethod
    def available(cls):
        return cls.status(load=True) == "ready"

    @classmethod
    def get(cls):
        if cls._instance is None:
            portable = os.path.join(model_registry.models_dir(),
                                    "deepcrispr_offtar_pt_cnn_reg.portable.npz")
            cls._instance = DeepCrisprForward(portable)
        return cls._instance

    def predict(self, guide, off_spacer, pam=None, off_pam=None):
        return self.get().predict(guide, off_spacer, pam, off_pam)

    def predict_pairs(self, guide, off_spacers, pam=None, off_pam=None):
        """Score one guide against multiple off-targets in one forward pass."""
        if not off_spacers:
            return []
        x_on, x_off = [], []
        for off_spacer in off_spacers:
            on_input, off_input = deepcrispr_make_inputs(
                guide, pam, off_spacer, off_pam)
            x_on.append(on_input)
            x_off.append(off_input)
        return self.get().predict_encoded(
            np.stack(x_on), np.stack(x_off)).tolist()

    def predict_encoded(self, x_on, x_off):
        return self.get().predict_encoded(x_on, x_off)


def crispr_m_status(load=True):
    path = model_registry.get_model_path("crispr_m")
    if not path or not os.path.isfile(path):
        return "not_downloaded"
    try:
        if load:
            CrisprMPredictor.get()
        import h5py
        return "ready"
    except Exception:
        return "load_error"


def model_statuses(load=False):
    return {
        "crispr_m": crispr_m_status(load=load),
        "deepcrispr": DeepCrisprPredictor.status(load=load),
        "deepcas12a": deepcas12a_status(load=load),
        "deepcpf1": deepcpf1_status(load=load),
        "tiger": _TigerPredictor.status(load=load),
    }


def predictor_status(model_key, load=False):
    """Unified status for the local predictors."""
    key = (model_key or "").lower()
    if key == "crispr_m":
        return crispr_m_status(load=load)
    if key == "deepcrispr":
        return DeepCrisprPredictor.status(load=load)
    if key == "deepcas12a":
        return deepcas12a_status(load=load)
    if key == "deepcpf1":
        return deepcpf1_status(load=load)
    if key in ("tiger", "tiger13"):
        return _TigerPredictor.status(load=load)
    raise ValueError("Unknown predictor: %s" % model_key)


def deep_model_off_target_specificity(guide, off_pairs, model_key="crispr_m",
                                      assume_one_primary=True):
    """Aggregate deep-model off-target activity like GuideScan2's CFD sum."""
    if not off_pairs:
        return 1.0
    if model_key == "crispr_m":
        predictor = CrisprMPredictor.get()
        off_spacers = [off_spacer for off_spacer, _pam in off_pairs]
        scores = predictor.predict_pairs(
            guide, off_spacers, pam=off_pairs[0][1])
        has_perfect = False
        for score in scores:
            if score >= 0.999999:
                has_perfect = True
        total = sum(scores)
        if assume_one_primary and has_perfect:
            total = max(0.0, total - 1.0)
        return 1.0 / (1.0 + total)
    if model_key == "deepcrispr":
        # .get() returns the cached DeepCrisprForward instance, which does not
        # expose predict_pairs; use the predictor facade so the batch inference
        # (and the fallback to CFD on failure) works as intended.
        predictor = DeepCrisprPredictor()
        off_spacers = [off_spacer for off_spacer, _pam in off_pairs]
        scores = predictor.predict_pairs(
            guide, off_spacers, pam=off_pairs[0][1])
        has_perfect = False
        activities = []
        for score in scores:
            activity = max(0.0, float(score))
            activities.append(activity)
            if activity >= 0.999999:
                has_perfect = True
        total = sum(activities)
        if assume_one_primary and has_perfect:
            total = max(0.0, total - 1.0)
        return 1.0 / (1.0 + total)
    raise ValueError("Unknown deep model: %s" % model_key)


# ---------------------------------------------------------------------------
# DeepCas12a (AsCas12a on-target efficiency)
# ---------------------------------------------------------------------------
#
# The upstream paper encodes a 34 nt target-context sequence as
# 4 nt upstream + TTTV PAM + 23 nt protospacer + 3 nt downstream, plus two
# 34-character epigenetic channels: methylation status and DNase accessibility.
# A -> methylated/accessible, N -> unmethylated/not accessible.  When a caller
# has no epigenetic track, all N is the safe missing-value encoding used by the
# upstream example data.


_DC12_NT = {
    "A": (1, 0, 0, 0),
    "C": (0, 1, 0, 0),
    "G": (0, 0, 1, 0),
    "T": (0, 0, 0, 1),
    "U": (0, 0, 0, 1),
    "N": (0, 0, 0, 0),
}


def _dc12_clean(seq):
    return (seq or "").upper().replace("U", "T")


def encode_deepcas12a_inputs(seq34, methylation=None, dnase=None):
    """Encode one 34 nt DeepCas12a input as a (6, 34) float32 array.

    Returns None when the input cannot be represented by the model.  Channels
    are the upstream one-hot (4) plus methylation (1) and DNase (1), matching
    the upstream ``Episgt`` encoder.
    """
    seq = _dc12_clean(seq34)
    if len(seq) != 34:
        return None
    methylation = _dc12_clean(methylation or "N" * 34)
    dnase = _dc12_clean(dnase or "N" * 34)
    if len(methylation) != 34 or len(dnase) != 34:
        return None

    seq_rows = []
    for base in seq:
        row = _DC12_NT.get(base)
        if row is None:
            return None
        seq_rows.append(row)
    epi_map = {"A": 1.0, "N": 0.0}
    meth_rows = [[epi_map.get(c, 0.0)] for c in methylation]
    dnase_rows = [[epi_map.get(c, 0.0)] for c in dnase]
    matrix = []
    for seq_row, meth_row, dnase_row in zip(seq_rows, meth_rows, dnase_rows):
        matrix.append(list(seq_row) + meth_row + dnase_row)
    # (positions, channels) -> (channels, positions), the shape consumed by the
    # VisionTransformer after the caller adds batch and image channels.
    return np.asarray(matrix, dtype=np.float32).transpose(1, 0)


class DeepCas12aPredictor:
    """PyTorch inference for the local DeepCas12a fold checkpoints."""

    _instance = None

    def __init__(self, checkpoint_path=None):
        import torch
        from scoring.deepcas12a_model import VisionTransformer

        self.torch = torch
        self.checkpoint_path = (
            checkpoint_path or model_registry.get_model_path("deepcas12a")
        )
        if not self.checkpoint_path or not os.path.isfile(self.checkpoint_path):
            raise FileNotFoundError("DeepCas12a checkpoint not found")
        self.model = VisionTransformer()
        self.model.load_state_dict(
            torch.load(self.checkpoint_path, map_location="cpu"))
        self.model.eval()

    @classmethod
    def available(cls):
        try:
            return cls.status() == "ready"
        except Exception:
            return False

    @classmethod
    def status(cls):
        try:
            import torch
        except Exception:
            return "dependency_missing"
        path = model_registry.get_model_path("deepcas12a")
        if not path or not os.path.isfile(path):
            return "not_downloaded"
        try:
            cls.get()
            return "ready"
        except Exception:
            return "load_error"

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _encode_batch(self, records):
        encoded = [
            encode_deepcas12a_inputs(
                record[0], record[1], record[2])
            for record in records
        ]
        if any(item is None for item in encoded):
            raise ValueError("DeepCas12a requires three 34-character records")
        x = np.stack(encoded)[:, None, :, :]
        return self.torch.tensor(x, dtype=self.torch.float32)

    def predict(self, seq34, methylation=None, dnase=None):
        """Return the class-1 (high-activity) probability in [0, 1]."""
        methylation = methylation or "N" * 34
        dnase = dnase or "N" * 34
        with self.torch.no_grad():
            x = self._encode_batch([(seq34, methylation, dnase)])
            logits = self.model.forward_logits(x)
            prob = self.torch.softmax(logits, dim=1)[0, 1]
            return float(prob.cpu().numpy())

    def predict_records(self, records):
        """Score ``[(seq, methylation, dnase), ...]`` in one batch."""
        if not records:
            return []
        with self.torch.no_grad():
            x = self._encode_batch(records)
            logits = self.model.forward_logits(x)
            probs = self.torch.softmax(logits, dim=1)[:, 1]
            return probs.cpu().numpy().tolist()


class DeepCpf1Predictor:
    """NumPy inference for the sequence-only DeepCpf1 checkpoint."""

    _instance = None

    @classmethod
    def available(cls):
        try:
            return cls.status() == "ready"
        except Exception:
            return False

    @classmethod
    def status(cls):
        path = model_registry.get_model_path("deepcpf1")
        if not path or not os.path.isfile(path):
            return "not_downloaded"
        try:
            cls.get()
            return "ready"
        except Exception:
            return "load_error"

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = DeepCpf1Forward()
        return cls._instance

    def predict(self, seq34):
        return self.get().predict(seq34)

    def predict_records(self, sequences):
        return self.get().predict_records(sequences)


def deepcpf1_status(load=True):
    if load:
        return DeepCpf1Predictor.status()
    path = model_registry.get_model_path("deepcpf1")
    if not path or not os.path.isfile(path):
        return "not_downloaded"
    return "ready"


def deepcas12a_status(load=True):
    if load:
        return DeepCas12aPredictor.status()
    path = model_registry.get_model_path("deepcas12a")
    if not path or not os.path.isfile(path):
        return "not_downloaded"
    return "ready"
