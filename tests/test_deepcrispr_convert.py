#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the TensorFlow-free DeepCRISPR checkpoint converter."""

import os
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "shared"))

import scoring.deepcrispr_convert as convert  # noqa: E402
import scoring.model_registry as model_registry  # noqa: E402


def _varint(value):
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _varint_field(field, value):
    return _varint((field << 3) | 0) + _varint(value)


def _length_field(field, payload):
    return _varint((field << 3) | 2) + _varint(len(payload)) + payload


def _shape_message(shape):
    out = bytearray()
    for dim in shape:
        out += _length_field(2, _varint_field(1, dim))
    return bytes(out)


def _entry_message(dtype, shape, offset, size):
    return (
        _varint_field(1, dtype)
        + _length_field(2, _shape_message(shape))
        + _varint_field(4, offset)
        + _varint_field(5, size)
    )


def _table_entry(key, value):
    return _varint(0) + _varint(len(key)) + _varint(len(value)) + key + value


class CheckpointParserTests(unittest.TestCase):
    def test_index_and_tensor_round_trip(self):
        weights = np.arange(4, dtype="<f4").reshape(1, 2, 2)
        bias = np.array([1.5, -2.0], dtype="<f4")
        data = weights.tobytes() + bias.tobytes()
        index = (
            _table_entry(b"sg/e_1/w", _entry_message(1, (1, 2, 2), 0, 16))
            + _table_entry(b"sg/e_1/b", _entry_message(1, (2,), 16, 8))
            + b"\0\0\0\0"
        )
        entries = dict(convert._index_entries(index))
        self.assertEqual(set(entries), {b"sg/e_1/w", b"sg/e_1/b"})
        parsed = convert._read_tensor(data, "sg/e_1/w", entries[b"sg/e_1/w"])
        np.testing.assert_array_equal(parsed, weights)

    def test_rejects_unsupported_wire_type(self):
        with self.assertRaises(ValueError):
            list(convert._fields(b"\x0f"))

    def test_content_digest_is_order_independent(self):
        first = {"b": np.array([2], dtype="<f4"),
                 "a": np.array([1], dtype="<f4")}
        second = {"a": np.array([1], dtype="<f4"),
                  "b": np.array([2], dtype="<f4")}
        self.assertEqual(convert.content_digest(first),
                         convert.content_digest(second))


class RealArchiveTests(unittest.TestCase):
    RAW = os.path.join(ROOT, "models", "deepcrispr_offtar_pt_cnn_reg.tar.gz")
    PORTABLE = os.path.join(
        ROOT, "models", "deepcrispr_offtar_pt_cnn_reg.portable.npz")

    @unittest.skipUnless(
        os.path.isfile(RAW) and os.path.isfile(PORTABLE),
        "local DeepCRISPR checkpoint archive is not available")
    def test_converts_to_the_published_portable_weights(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = os.path.join(tmp, convert.PORTABLE_NAME)
            convert.convert_tar_gz(self.RAW, output)
            with np.load(output, allow_pickle=False) as data:
                produced = {key: data[key] for key in data.files}
        with np.load(self.PORTABLE, allow_pickle=False) as data:
            expected = {key: data[key] for key in data.files}
        self.assertEqual(set(produced), set(expected))
        for key in expected:
            np.testing.assert_array_equal(produced[key], expected[key])
        self.assertEqual(convert.content_digest(produced),
                         convert.EXPECTED_CONTENT_SHA256)


class RegistryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patcher = mock.patch.object(
            model_registry, "MODEL_DIR", self.temp.name)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _sparse(self, name, size):
        path = os.path.join(self.temp.name, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.truncate(size)
        return path

    def test_status_requires_portable_weights(self):
        info = model_registry.MODELS["deepcrispr"]
        self._sparse(info["file"], info["expected_bytes"])
        details = model_registry.get_model_status_details("deepcrispr")
        self.assertEqual(details["status"], "needs_conversion")
        self.assertIn("portable", details["paths"])

    def test_setup_converts_an_existing_raw_archive(self):
        info = model_registry.MODELS["deepcrispr"]
        raw = self._sparse(info["file"], info["expected_bytes"])
        portable = model_registry._deepcrispr_portable_path()

        def fake_convert(archive_path, output_path):
            self.assertEqual(archive_path, raw)
            with open(output_path, "wb") as handle:
                handle.truncate(info["portable_expected_bytes"])
            return output_path

        with mock.patch("scoring.deepcrispr_convert.convert_tar_gz",
                        side_effect=fake_convert) as converter:
            returned = model_registry.setup_model("deepcrispr")
        self.assertEqual(returned, raw)
        converter.assert_called_once()
        self.assertTrue(os.path.isfile(portable))
        self.assertEqual(
            model_registry.get_model_status_details("deepcrispr")["status"],
            "ready")

    def test_download_alias_delegates_to_setup(self):
        with mock.patch.object(
                model_registry, "setup_model", return_value="model.npz") as setup:
            returned = model_registry.download_model("deepcrispr")
        self.assertEqual(returned, "model.npz")
        setup.assert_called_once_with("deepcrispr", None, None)

    def test_delete_removes_raw_and_portable_files(self):
        info = model_registry.MODELS["deepcrispr"]
        raw = self._sparse(info["file"], info["expected_bytes"])
        portable = self._sparse(
            os.path.basename(model_registry._deepcrispr_portable_path()),
            info["portable_expected_bytes"])
        model_registry.delete_model("deepcrispr")
        self.assertFalse(os.path.exists(raw))
        self.assertFalse(os.path.exists(portable))
