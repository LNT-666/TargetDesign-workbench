#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NumPy forward pass for the sequence-only DeepCpf1 on-target model.

DeepCpf1 predicts Cpf1/Cas12a indel frequency from a 34 nt target-context
window arranged as 4 nt upstream + TTTV PAM + 23 nt protospacer + 3 nt
downstream.  The upstream Keras/Theano checkpoint stores its Conv1D kernel in
theano order, which requires reversing the filter along the length axis when
the same cross-correlation is reproduced in NumPy.
"""

import os
import re

import numpy as np

import scoring.model_registry as model_registry


_NT_INDEX = {"A": 0, "C": 1, "G": 2, "T": 3}
_SEQ_LEN = 34


def encode_seq(seq34):
    """One-hot encode a 34 nt sequence as a (34, 4) float32 array.

    Column order follows DeepCpf1's original ``PREPROCESS`` function:
    A, C, G, T.  Raises ValueError for an invalid input so callers can treat
    it as a clean fallback trigger.
    """
    seq = (seq34 or "").upper().replace("U", "T")
    if len(seq) != _SEQ_LEN:
        raise ValueError("DeepCpf1 requires a 34 nt target-context sequence")
    if not all(base in _NT_INDEX for base in seq):
        raise ValueError("DeepCpf1 accepts only A/C/G/T sequence characters")
    out = np.zeros((_SEQ_LEN, 4), dtype=np.float32)
    for pos, base in enumerate(seq):
        out[pos, _NT_INDEX[base]] = 1.0
    return out


class DeepCpf1Forward:
    """Loads DeepCpf1 HDF5 weights and runs the CNN without TensorFlow."""

    _instance = None

    def __init__(self, h5_path=None):
        self.h5_path = h5_path or model_registry.get_model_path("deepcpf1")
        if not self.h5_path or not os.path.isfile(self.h5_path):
            raise FileNotFoundError("DeepCpf1 model file not found")
        try:
            import h5py
        except ImportError:
            raise RuntimeError("h5py is required to load the DeepCpf1 model")
        self.weights = {}
        with h5py.File(self.h5_path, "r") as handle:
            handle.visititems(self._collect)
        self._load_layers()

    @staticmethod
    def _layer_index(name):
        match = re.search(r"_(\d+)(?:_|$)", name)
        return int(match.group(1)) if match else 0

    def _collect(self, name, obj):
        import h5py
        if isinstance(obj, h5py.Dataset):
            self.weights[name] = obj[()]

    def _load_layers(self):
        conv_w = []
        conv_b = []
        dense = []
        for name, value in self.weights.items():
            if name.endswith("_W") and value.ndim == 4:
                conv_w.append((name, value))
            elif name.endswith("_b") and value.ndim == 1:
                group = name.rsplit("/", 1)[0]
                if group.startswith("convolution1d"):
                    conv_b.append((name, value))
            elif name.endswith("_W") and value.ndim == 2:
                dense.append((name, value))

        if len(conv_w) != 1:
            raise ValueError(
                "Expected one DeepCpf1 Conv1D weight, found %d" % len(conv_w))
        self.conv_kernel = conv_w[0][1]
        if self.conv_kernel.shape[1] != 1 or self.conv_kernel.ndim != 4:
            raise ValueError(
                "Unexpected DeepCpf1 Conv1D weight shape: %s"
                % (self.conv_kernel.shape,))

        conv_group = conv_w[0][0].rsplit("/", 1)[0]
        conv_bias = next((value for name, value in conv_b
                          if name.rsplit("/", 1)[0] == conv_group), None)
        if conv_bias is None:
            raise ValueError("Missing DeepCpf1 Conv1D bias")
        self.conv_bias = conv_bias.astype(np.float32)

        dense.sort(key=lambda item: (self._layer_index(item[0]), item[0]))
        if len(dense) != 4:
            raise ValueError(
                "Expected four DeepCpf1 Dense weights, found %d" % len(dense))
        self.dense = []
        for name, weight in dense:
            bias_name = name[:-2] + "_b"
            if bias_name not in self.weights:
                raise ValueError("Missing DeepCpf1 bias: %s" % bias_name)
            self.dense.append(
                (weight.astype(np.float32),
                 self.weights[bias_name].astype(np.float32)))

        expected_dense = [(1200, 80), (80, 40), (40, 40), (40, 1)]
        for index, ((weight, _bias), expected) in enumerate(
                zip(self.dense, expected_dense)):
            if tuple(weight.shape) != expected:
                raise ValueError(
                    "Unexpected DeepCpf1 Dense weight shape %s at layer %d; "
                    "expected %s" % (weight.shape, index, expected))

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _conv_pool(self, x):
        # Theano stores Conv1D weights as (filter_length, 1, in_ch, out_ch)
        # and applies cross-correlation.  NumPy's sliding-window form needs
        # the length axis reversed to reproduce that operation.
        kernel = np.flip(self.conv_kernel, axis=0)[:, 0, :, :]
        batch = x.shape[0]
        conv = np.zeros((batch, _SEQ_LEN - kernel.shape[0] + 1,
                         kernel.shape[2]), dtype=np.float32)
        for pos in range(conv.shape[1]):
            window = x[:, pos:pos + kernel.shape[0], :]
            conv[:, pos, :] = np.einsum(
                "nkc,kco->no", window, kernel, optimize=True)
        conv = np.maximum(conv + self.conv_bias, 0.0)
        pooled = conv.reshape(
            batch, conv.shape[1] // 2, 2, conv.shape[2]).mean(axis=2)
        return pooled.reshape(batch, -1)

    def _predict_encoded(self, x):
        hidden = self._conv_pool(x)
        for index, (weight, bias) in enumerate(self.dense):
            hidden = hidden @ weight + bias
            if index < len(self.dense) - 1:
                hidden = np.maximum(hidden, 0.0)
        return hidden.reshape(-1)

    def predict(self, seq34):
        x = encode_seq(seq34)[None, :, :]
        return float(self._predict_encoded(x)[0])

    def predict_records(self, sequences):
        if not sequences:
            return []
        encoded = [encode_seq(seq) for seq in sequences]
        x = np.stack(encoded, axis=0)
        return self._predict_encoded(x).tolist()
