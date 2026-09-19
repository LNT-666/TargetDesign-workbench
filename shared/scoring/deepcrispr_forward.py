#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NumPy forward pass for the DeepCRISPR off-target regression CNN."""

import json
import math
import os

import numpy as np

import scoring.model_registry as model_registry


PORTABLE_NAME = "deepcrispr_offtar_pt_cnn_reg.portable.npz"
BN_EPS = 1e-5

_NUCLEOTIDE_MAP = {
    "A": (1, 0, 0, 0),
    "C": (0, 1, 0, 0),
    "G": (0, 0, 1, 0),
    "T": (0, 0, 0, 1),
}


def encode_23mer(seq, epi_channels=None):
    """Encode one 23 nt window as 8 channels: 4 one-hot + 4 optional epi."""
    seq = (seq or "").upper().replace("U", "T")
    if len(seq) < 23:
        seq = seq + "N" * (23 - len(seq))
    seq = seq[:23]
    rows = []
    for base in seq:
        rows.append(_NUCLEOTIDE_MAP.get(base, (0, 0, 0, 0)))
    channels = np.asarray(rows, dtype=np.float32).T
    if epi_channels is not None:
        epi = []
        for channel in epi_channels:
            channel = (channel or "").upper()[:23].ljust(23, "N")
            epi.append(np.array([1.0 if base == "A" else 0.0 for base in channel],
                                dtype=np.float32))
        channels = np.vstack([channels] + epi)
    else:
        channels = np.vstack([channels, np.zeros((4, 23), dtype=np.float32)])
    return channels


def make_inputs(guide_spacer, pam, off_spacer, off_pam):
    """Build on/off 23 nt inputs with zero epigenetic channels."""
    on_seq = guide_spacer.upper().replace("U", "T")[:20]
    off_seq = off_spacer.upper().replace("U", "T")[:20]
    pam = (pam or "N").upper().replace("U", "T")[:3].ljust(3, "N")
    off_pam = (off_pam or "N").upper().replace("U", "T")[:3].ljust(3, "N")
    return (encode_23mer(on_seq + pam),
            encode_23mer(off_seq + off_pam))


def _conv1d(x, kernel, bias, stride, padding):
    """1D convolution equivalent to TF Conv2D with H=1, NHWC."""
    n, in_ch, length = x.shape
    kw = kernel.shape[0]
    out_ch = kernel.shape[2]
    if padding == "SAME":
        out_len = int(math.ceil(length / float(stride)))
        total_pad = max(0, (out_len - 1) * stride + kw - length)
        pad_left = total_pad // 2
        pad_right = total_pad - pad_left
    else:
        out_len = (length - kw) // stride + 1
        pad_left = pad_right = 0
    if pad_left or pad_right:
        x = np.pad(x, ((0, 0), (0, 0), (pad_left, pad_right)))
    out = np.zeros((n, out_ch, out_len), dtype=np.float32)
    for pos in range(out_len):
        start = pos * stride
        window = x[:, :, start:start + kw]
        out[:, :, pos] = np.einsum("bik,kio->bo", window, kernel,
                                   optimize=True) + bias
    return out


def _batch_norm(x, moving_mean, moving_variance, beta=None, gamma=None):
    def broadcast(param, default):
        if param is None:
            param = np.full(x.shape[1], default, dtype=np.float32)
        else:
            param = np.asarray(param, dtype=np.float32).reshape(-1)
            if param.size == 1 and x.shape[1] != 1:
                param = np.full(x.shape[1], param[0], dtype=np.float32)
        return param.reshape((1, -1, 1))

    scale = broadcast(gamma, 1.0)
    offset = broadcast(beta, 0.0)
    moving_mean = broadcast(moving_mean, 0.0)
    moving_variance = broadcast(moving_variance, 0.0)
    return (x - moving_mean) / np.sqrt(moving_variance + BN_EPS) * scale + offset


class DeepCrisprForward:
    """Loads the converted checkpoint weights and runs the CNN in NumPy."""

    def __init__(self, npz_path=None):
        self.path = npz_path or os.path.join(model_registry.models_dir(),
                                             PORTABLE_NAME)
        if not os.path.isfile(self.path):
            raise FileNotFoundError("DeepCRISPR portable model not found: %s"
                                    % self.path)
        with np.load(self.path, allow_pickle=False) as data:
            self.weights = {key: data[key] for key in data.files}
        self._check_shapes()

    def _w(self, name):
        return self.weights[name]

    def _check_shapes(self):
        for side in ("sg", "ot"):
            self._w("%s/e_1/w" % side).shape == (1, 3, 8, 32)
        self._w("e_9/w").shape == (1, 1, 1024, 1)

    def _encoder(self, x, side):
        betas = [None] + [self._w("%s/beta_%d" % (side, i))
                          .reshape((1, -1, 1)) for i in range(1, 6)]
        strides = {1: 1, 2: 2, 3: 1, 4: 2, 5: 1}
        current = x
        for i in range(1, 6):
            kernel = self._w("%s/e_%d/w" % (side, i))[0]
            bias = self._w("%s/e_%d/b" % (side, i))
            current = _conv1d(current, kernel, bias, strides[i], "SAME")
            current = _batch_norm(
                current,
                self._w("%s/ebn_%du/moving_mean" % (side, i)),
                self._w("%s/ebn_%du/moving_variance" % (side, i)))
            current = np.maximum(0.0, current + betas[i])
        return current

    def _classifier(self, features):
        configs = [
            ("e_6", 512, 2, "SAME", "ebn_6l"),
            ("e_7", 512, 1, "SAME", "ebn_7l"),
            ("e_8", 1024, 1, "VALID", "ebn_8l"),
        ]
        current = features
        for name, _out_ch, stride, padding, bn in configs:
            kernel = self._w("%s/w" % name)[0]
            bias = self._w("%s/b" % name)
            current = _conv1d(current, kernel, bias, stride, padding)
            current = _batch_norm(
                current,
                self._w("%s/moving_mean" % bn),
                self._w("%s/moving_variance" % bn),
                beta=self._w("%s/beta" % bn))
            current = np.maximum(0.0, current)
        kernel = self._w("e_9/w")[0]
        bias = self._w("e_9/b")
        current = _conv1d(current, kernel, bias, 1, "VALID")
        return current.reshape(current.shape[0])

    def predict_encoded(self, x_on, x_off):
        """x_on/x_off have shape (batch, 8, 23)."""
        if x_on.ndim == 2:
            x_on = x_on[None]
        if x_off.ndim == 2:
            x_off = x_off[None]
        sg = self._encoder(x_on.astype(np.float32), "sg")
        ot = self._encoder(x_off.astype(np.float32), "ot")
        features = np.concatenate([sg, ot], axis=1)
        return self._classifier(features)

    def predict(self, guide_spacer, off_spacer, pam=None, off_pam=None):
        x_on, x_off = make_inputs(guide_spacer, pam, off_spacer, off_pam)
        return float(self.predict_encoded(x_on, x_off)[0])
