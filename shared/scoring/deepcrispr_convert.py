#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Convert the DeepCRISPR TF1 checkpoint without TensorFlow.

The published DeepCRISPR archive contains a TensorFlow 1.x checkpoint
(``*.index`` plus ``*.data-*``).  The runtime only needs the portable NumPy
weights, so this module reads the small TensorFlow tensor-bundle index directly
instead of requiring a multi-hundred-megabyte TensorFlow installation.

Only the container pieces used by DeepCRISPR are implemented: the index is a
single uncompressed tensor-bundle block and the checkpoint has one data shard.
The parsed tensors are compared against a canonical content digest before the
portable file is published, so an upstream checkpoint change fails loudly
instead of silently changing scores.
"""

from __future__ import annotations

import hashlib
import os
import tarfile
import tempfile

import numpy as np


PORTABLE_NAME = "deepcrispr_offtar_pt_cnn_reg.portable.npz"
WEIGHT_PREFIXES = ("sg/", "ot/", "e_", "ebn_")
SKIP_SUFFIXES = ("/Adam", "/Adam_1", "beta1_power", "beta2_power")
EXPECTED_WEIGHT_COUNT = 67
EXPECTED_CONTENT_SHA256 = (
    "30953303affa7b01489d59c0620bb92fe65e8d52515a578b6c4d5b1d170f52b6"
)

# TensorFlow DataType enum values used by tensor-bundle entries.
_DTYPES = {
    1: np.dtype("<f4"),
    2: np.dtype("<f8"),
    3: np.dtype("<i4"),
    4: np.dtype("u1"),
    5: np.dtype("<i2"),
    6: np.dtype("i1"),
    8: np.dtype("<c8"),
    9: np.dtype("<i8"),
    10: np.dtype("?"),
    14: np.dtype("<f2"),
    17: np.dtype("<u2"),
    18: np.dtype("<c16"),
    19: np.dtype("<f2"),
    22: np.dtype("<u4"),
    23: np.dtype("<u8"),
}


def _varint(buf, pos):
    value = 0
    shift = 0
    while True:
        if pos >= len(buf):
            raise ValueError("truncated varint")
        byte = buf[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return value, pos
        shift += 7
        if shift > 70:
            raise ValueError("varint is too long")


def _fields(buf):
    """Yield ``(field_number, wire_type, value)`` from a protobuf message."""
    pos = 0
    while pos < len(buf):
        tag, pos = _varint(buf, pos)
        field = tag >> 3
        wire = tag & 0x07
        if wire == 0:
            value, pos = _varint(buf, pos)
        elif wire == 1:
            value = buf[pos:pos + 8]
            pos += 8
        elif wire == 2:
            length, pos = _varint(buf, pos)
            value = buf[pos:pos + length]
            pos += length
        elif wire == 5:
            value = buf[pos:pos + 4]
            pos += 4
        else:
            raise ValueError("unsupported protobuf wire type %d" % wire)
        if pos > len(buf):
            raise ValueError("truncated protobuf field")
        yield field, wire, value


def _shape_from_message(buf):
    """Decode ``TensorShapeProto`` into a tuple, or ``None`` for unknown rank."""
    dims = []
    for field, wire, value in _fields(buf):
        if field == 2 and wire == 2:
            dim = 0
            for dim_field, dim_wire, dim_value in _fields(value):
                if dim_field == 1 and dim_wire == 0:
                    dim = dim_value
            dims.append(dim)
        elif field == 3 and wire == 0 and value:
            return None
    return tuple(dims)


def _entry_from_message(buf):
    entry = {"shard": 0, "slices": False}
    for field, wire, value in _fields(buf):
        if field == 1 and wire == 0:
            entry["dtype"] = value
        elif field == 2 and wire == 2:
            entry["shape"] = _shape_from_message(value)
        elif field == 3 and wire == 0:
            entry["shard"] = value
        elif field == 4 and wire == 0:
            entry["offset"] = value
        elif field == 5 and wire == 0:
            entry["size"] = value
        elif field == 7:
            entry["slices"] = True
    return entry


def _index_entries(index_bytes):
    """Return the tensor-bundle index entries as ``(name, entry)`` pairs."""
    entries = []
    pos = 0
    previous_key = b""
    while pos < len(index_bytes) - 4:
        start = pos
        try:
            shared, pos = _varint(index_bytes, pos)
            non_shared, pos = _varint(index_bytes, pos)
            value_length, pos = _varint(index_bytes, pos)
            if pos + non_shared + value_length > len(index_bytes):
                break
            key = previous_key[:shared] + index_bytes[pos:pos + non_shared]
            pos += non_shared
            value = index_bytes[pos:pos + value_length]
            pos += value_length
        except ValueError:
            if start == 0:
                raise
            break
        previous_key = key
        if key:
            entries.append((key, _entry_from_message(value)))
    if not entries:
        raise ValueError("TensorFlow checkpoint index contains no tensor entries")
    return entries


def _read_tensor(data_bytes, name, entry):
    if entry.get("slices"):
        raise ValueError("sliced checkpoint tensor is not supported: %s" % name)
    if entry.get("shard", 0) != 0:
        raise ValueError("multi-shard checkpoint is not supported: %s" % name)
    dtype = _DTYPES.get(entry.get("dtype"))
    if dtype is None:
        raise ValueError("unsupported checkpoint dtype for %s: %r"
                         % (name, entry.get("dtype")))
    shape = entry.get("shape")
    if shape is None:
        raise ValueError("unknown-rank checkpoint tensor: %s" % name)
    offset = entry.get("offset", 0)
    size = entry.get("size", 0)
    if offset < 0 or size < 0 or offset + size > len(data_bytes):
        raise ValueError("checkpoint tensor points outside the data file: %s"
                         % name)
    expected = dtype.itemsize
    for dim in shape:
        expected *= dim
    if expected != size:
        raise ValueError(
            "checkpoint tensor size mismatch for %s: shape %s needs %d bytes, "
            "entry has %d" % (name, shape, expected, size))
    array = np.frombuffer(data_bytes[offset:offset + size], dtype=dtype)
    return array.reshape(shape).copy()


def content_digest(weights):
    """Return a stable SHA256 over keys, dtypes, shapes and tensor bytes."""
    digest = hashlib.sha256()
    for name in sorted(weights):
        array = np.ascontiguousarray(weights[name])
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(array.dtype).encode("ascii"))
        digest.update(b"\0")
        digest.update(str(array.shape).encode("ascii"))
        digest.update(b"\0")
        digest.update(array.tobytes())
    return digest.hexdigest()


def convert_checkpoint(index_bytes, data_bytes, output_path):
    """Convert one tensor-bundle index/data pair into the portable npz."""
    weights = {}
    for raw_name, entry in _index_entries(index_bytes):
        name = raw_name.decode("utf-8")
        if not name.startswith(WEIGHT_PREFIXES):
            continue
        if any(name.endswith(suffix) for suffix in SKIP_SUFFIXES):
            continue
        weights[name] = _read_tensor(data_bytes, name, entry)

    if len(weights) != EXPECTED_WEIGHT_COUNT:
        raise ValueError(
            "DeepCRISPR conversion produced %d weights, expected %d"
            % (len(weights), EXPECTED_WEIGHT_COUNT))
    digest = content_digest(weights)
    if digest != EXPECTED_CONTENT_SHA256:
        raise ValueError(
            "DeepCRISPR checkpoint content digest mismatch: got %s, expected %s"
            % (digest, EXPECTED_CONTENT_SHA256))

    output_path = os.path.abspath(output_path)
    output_dir = os.path.dirname(output_path)
    os.makedirs(output_dir, exist_ok=True)
    handle, temp_path = tempfile.mkstemp(
        prefix=".deepcrispr-convert-", suffix=".npz", dir=output_dir)
    os.close(handle)
    try:
        with open(temp_path, "wb") as output:
            np.savez(output, **{name: weights[name] for name in sorted(weights)})
        os.replace(temp_path, output_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
    return output_path


def convert_tar_gz(archive_path, output_path):
    """Read the DeepCRISPR archive in memory and write the portable npz."""
    with tarfile.open(archive_path, "r:gz") as archive:
        members = [member for member in archive.getmembers() if member.isfile()]
        index_members = [member for member in members
                         if member.name.endswith(".index")]
        data_members = [member for member in members
                        if ".data-" in member.name]
        if len(index_members) != 1 or len(data_members) != 1:
            raise ValueError(
                "DeepCRISPR archive must contain exactly one .index and one "
                ".data-* file (found %d and %d)"
                % (len(index_members), len(data_members)))
        index_file = archive.extractfile(index_members[0])
        data_file = archive.extractfile(data_members[0])
        if index_file is None or data_file is None:
            raise ValueError("DeepCRISPR archive contains unreadable checkpoint files")
        index_bytes = index_file.read()
        data_bytes = data_file.read()
    return convert_checkpoint(index_bytes, data_bytes, output_path)
