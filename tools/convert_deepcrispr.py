#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Convert the DeepCRISPR TF1 checkpoint into a portable NumPy model file.

Run inside the Python 3.10 backup environment with TensorFlow:

    pip install tensorflow==2.10.0 numpy
    python tools\\convert_deepcrispr.py

The converter also validates the NumPy forward pass against a TensorFlow
reference graph using the upstream example file.
"""

import argparse
import os
import sys

import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "shared"))
from scoring.deepcrispr_forward import (BN_EPS, DeepCrisprForward, encode_23mer)  # noqa: E402


WEIGHT_PREFIXES = ("sg/", "ot/", "e_", "ebn_")
SKIP_SUFFIXES = ("/Adam", "/Adam_1", "beta1_power", "beta2_power")


def read_checkpoint(reader, output_path):
    out = {}
    for name in sorted(reader.get_variable_to_shape_map()):
        if not name.startswith(WEIGHT_PREFIXES):
            continue
        if any(name.endswith(suffix) for suffix in SKIP_SUFFIXES):
            continue
        out[name] = reader.get_tensor(name)
    np.savez(output_path, **out)
    print("exported %d weight tensors to %s" % (len(out), output_path))
    return out


def load_example(path):
    rows = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 12:
                continue
            rows.append({
                "sg": parts[1],
                "sg_epi": parts[2:6],
                "ot": parts[6],
                "ot_epi": parts[7:11],
                "y": float(parts[11]),
            })
    return rows


def build_batch(rows, seq_key, epi_key):
    return np.stack([
        encode_23mer(row[seq_key], row[epi_key]) for row in rows
    ]).astype(np.float32)


def tf_reference_predict(weights, x_on, x_off):
    import tensorflow as tf

    tf.compat.v1.disable_eager_execution()
    tf.compat.v1.reset_default_graph()
    inputs_sg = tf.compat.v1.placeholder(tf.float32, [None, 1, 23, 8])
    inputs_ot = tf.compat.v1.placeholder(tf.float32, [None, 1, 23, 8])

    def conv(x, name, stride, padding):
        w = tf.constant(weights[name + "/w"])
        b = tf.constant(weights[name + "/b"])
        return tf.nn.conv2d(x, w, strides=[1, 1, stride, 1],
                            padding=padding) + b

    def batch_norm(x, name, beta=None):
        mean = tf.constant(weights[name + "/moving_mean"])
        var = tf.constant(weights[name + "/moving_variance"])
        offset = tf.constant(beta) if beta is not None else None
        return tf.nn.batch_normalization(x, mean, var, offset, None, BN_EPS)

    def encoder(x, side):
        betas = [tf.constant(weights["%s/beta_%d" % (side, i)])
                 for i in range(1, 6)]
        strides = {1: 1, 2: 2, 3: 1, 4: 2, 5: 1}
        for i in range(1, 6):
            x = conv(x, "%s/e_%d" % (side, i), strides[i], "SAME")
            x = batch_norm(x, "%s/ebn_%du" % (side, i))
            x = tf.nn.relu(x + betas[i - 1])
        return x

    sg = encoder(inputs_sg, "sg")
    ot = encoder(inputs_ot, "ot")
    h = tf.concat([sg, ot], axis=3)
    for name, stride, padding, bn in (
            ("e_6", 2, "SAME", "ebn_6l"),
            ("e_7", 1, "SAME", "ebn_7l"),
            ("e_8", 1, "VALID", "ebn_8l")):
        h = conv(h, name, stride, padding)
        h = batch_norm(h, bn, beta=weights[bn + "/beta"])
        h = tf.nn.relu(h)
    h = conv(h, "e_9", 1, "VALID")
    logits = tf.squeeze(h, axis=[1, 2, 3])
    with tf.compat.v1.Session() as sess:
        feed_on = x_on.transpose(0, 2, 1)[:, None, :, :]
        feed_off = x_off.transpose(0, 2, 1)[:, None, :, :]
        return sess.run(logits, feed_dict={
            inputs_sg: feed_on,
            inputs_ot: feed_off,
        })


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint",
                        default="models/offtar_pt_cnn_reg/model.ckpt-ptreg")
    parser.add_argument("--output",
                        default="models/deepcrispr_offtar_pt_cnn_reg.portable.npz")
    parser.add_argument("--example",
                        default="tests/data/deepcrispr_example.repiotrt")
    args = parser.parse_args()

    root = _ROOT
    checkpoint = os.path.join(root, args.checkpoint)
    output_path = os.path.join(root, args.output)

    import tensorflow as tf
    reader = tf.compat.v1.train.NewCheckpointReader(checkpoint)
    weights = read_checkpoint(reader, output_path)

    example_path = os.path.join(root, args.example)
    if not os.path.isfile(example_path):
        print("skipping validation: example file not found at", example_path)
        return
    rows = load_example(example_path)
    x_on = build_batch(rows, "sg", "sg_epi")
    x_off = build_batch(rows, "ot", "ot_epi")
    ref = tf_reference_predict(weights, x_on, x_off)
    model = DeepCrisprForward(output_path)
    preds = model.predict_encoded(x_on, x_off)
    diff = float(np.max(np.abs(preds - ref)))
    print("validation rows:", len(rows))
    print("max |numpy - tensorflow|:", diff)
    if diff > 1e-3:
        raise SystemExit("NumPy forward does not match TensorFlow reference")
    print("DeepCRISPR conversion validated")


if __name__ == "__main__":
    main()
