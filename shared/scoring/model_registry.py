#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local model registry used by the main GUI's model download tab."""

import os
import importlib.util
import shutil
import subprocess
import sys
import time
import urllib.request


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL_DIR = os.path.join(ROOT_DIR, "models")
RAW_GITHUB_PREFIX = "https://raw.githubusercontent.com/"
GITHUB_PROXY_PREFIX = "https://gh-proxy.com/"
HF_MIRROR_PREFIX = "https://hf-mirror.com/"

# Human-readable labels for the protein (nuclease) groups shown in the GUI.
PROTEIN_LABELS = {
    "cas9": "Cas9",
    "cas12a": "Cas12a / Cpf1",
    "tnpb": "TnpB (ISDra2)",
    "cas13": "Cas13 (RNA)",
}


MODELS = {
    "crispr_m": {
        "name": "CRISPR-M",
        "type": "file",
        "role": "off_target",
        "runtime": "numpy_h5py",
        "scope": ["cas9"],
        "protein": "cas9",
        "visible": True,
        "default": False,
        "file": "tcrispr_model.h5",
        "url": "https://raw.githubusercontent.com/lyotvincent/CRISPR-M/master/test/7visualization/tcrispr_model.h5",
        "expected_bytes": 20828208,
        "description": "Cas9 off-target deep learning ranking model (~20 MB)",
    },
    "deepcrispr": {
        "name": "DeepCRISPR",
        "type": "file",
        "role": "off_target",
        "runtime": "numpy",
        "scope": ["cas9"],
        "protein": "cas9",
        "visible": True,
        "default": False,
        "file": "deepcrispr_offtar_pt_cnn_reg.tar.gz",
        "url": "https://raw.githubusercontent.com/bm2-lab/DeepCRISPR/master/trained_models/offtar_pt_cnn_reg.tar.gz",
        "expected_bytes": 29160245,
        "description": "Cas9 off-target CNN model (~28 MB, TensorFlow 1.x)",
    },
    "crispai": {
        "name": "crispAI-aggregate",
        "type": "file",
        "role": "off_target",
        "runtime": "pytorch",
        "scope": ["cas9"],
        "protein": "cas9",
        "visible": True,
        "default": False,
        "file": "crispai.pt",
        "url": "https://raw.githubusercontent.com/furkanozdenn/crispr-offtarget-uncertainty/main/crispAI_score/model_checkpoint/epoch%3A19-best_valid_loss%3A0.270.pt",
        "expected_bytes": 10201336,
        "description": "crispAI uncertainty-aware off-target aggregate model (~10 MB)",
    },
    "deepcpf1": {
        "name": "DeepCpf1",
        "type": "file",
        "role": "on_target",
        "runtime": "numpy_h5py",
        "scope": ["cas12a", "cpf1"],
        "protein": "cas12a",
        "visible": True,
        "default": False,
        "file": "seq_deepcpf1_weights.h5",
        "url": "https://raw.githubusercontent.com/astroboi-SH-KWON/DeepCpf1_py3/master/weights/Seq_deepCpf1_weights.h5",
        "expected_bytes": 428168,
        "description": "DeepCpf1 sequence-only Cas12a/Cpf1 on-target model (~0.4 MB)",
    },
    "deepcas12a": {
        "name": "DeepCas12a",
        "type": "file",
        "role": "on_target",
        "runtime": "pytorch",
        "scope": ["cas12a", "cpf1"],
        "protein": "cas12a",
        "visible": True,
        "default": False,
        "file": "deepcas12a_fold1.pth",
        "url": "https://raw.githubusercontent.com/bm2-lab-submission/DeepCas12a/main/trained_model/fold1.pth",
        "expected_bytes": 23881156,
        "description": "DeepCas12a AsCas12a on-target CNN-Transformer fold 1 (~23 MB)",
    },
    "tiger": {
        "name": "TIGER (Cas13d)",
        "type": "savedmodel_dir",
        "role": "on_target",
        "runtime": "tensorflow",
        "scope": ["cas13", "cas13d"],
        "protein": "cas13",
        "visible": True,
        "default": False,
        "dir": "tiger",
        "url": "https://hf-mirror.com/spaces/Knowles-Lab/tiger",
        "source": {
            "kind": "hf_space",
            "owner": "Knowles-Lab",
            "repo": "tiger",
            "branch": "main",
        },
        "files": [
            {"path": "model/saved_model.pb", "expected_bytes": 242327},
            {"path": "model/variables/variables.data-00000-of-00001",
             "expected_bytes": 948103},
            {"path": "model/variables/variables.index", "expected_bytes": 877},
            {"path": "model/keras_metadata.pb", "expected_bytes": 13631},
            {"path": "model/fingerprint.pb", "expected_bytes": 55},
            {"path": "scoring_params.pkl", "expected_bytes": 706},
            {"path": "calibration_params.pkl", "expected_bytes": 885},
        ],
        "description": "TIGER Cas13d on/off-target deep-learning model (~1.2 MB, "
                       "downloaded via hf-mirror resolve)",
    },
    "teep": {
        "name": "TEEP",
        "type": "web",
        "role": "on_target",
        "runtime": "web_api",
        "scope": ["tnpb", "isdra2"],
        "protein": "tnpb",
        "visible": True,
        "default": False,
        "url": "https://www.tnpb.app",
        "description": "ISDra2 TnpB editing efficiency predictor (online API, no download)",
    },
}


def models_dir():
    return MODEL_DIR


def get_model_path(key):
    info = MODELS[key]
    if info["type"] in ("web", "external"):
        return None
    if info["type"] == "savedmodel_dir":
        return os.path.join(MODEL_DIR, info["dir"])
    return os.path.join(MODEL_DIR, info["file"])


def is_downloadable(info):
    """Return True for entries that expose a Download/Delete control.""" 
    return (info or {}).get("type") in ("file", "savedmodel_dir")


def _dir_files_present(info, target_dir):
    """Return True when every registered file exists with a matching size."""
    files = info.get("files") or []
    present = 0
    for item in files:
        path = os.path.join(target_dir, *item["path"].split("/"))
        found = os.path.isfile(path)
        if found:
            present += 1
        expected = item.get("expected_bytes")
        if found and expected and abs(os.path.getsize(path) - expected) > max(
                1, expected * 0.01):
            return False
    return present == len(files) and present > 0


def dir_download_progress(key):
    """Return ``(downloaded, total_bytes)`` for a directory-backed download.

    Sums the size of already-complete files plus the bytes written to the
    per-file ``.part`` staging files, so the GUI progress poll can track a
    multi-file download that models stored as a single file cannot.
    """
    info = MODELS.get(key) or {}
    if info.get("type") != "savedmodel_dir":
        return 0, 0
    files = info.get("files") or []
    target_dir = get_model_path(key)
    if not target_dir or not os.path.isdir(target_dir):
        return 0, 0
    total_bytes = sum(item.get("expected_bytes") or 0 for item in files)
    downloaded = 0
    for item in files:
        dest = os.path.join(target_dir, *item["path"].split("/"))
        if os.path.isfile(dest):
            downloaded += os.path.getsize(dest)
        part = dest + ".part"
        if os.path.isfile(part):
            downloaded += os.path.getsize(part)
    return downloaded, total_bytes


def get_model_status(key):
    info = MODELS[key]
    if info["type"] == "web":
        return "web_api"
    if info["type"] == "external":
        return "external"
    if info["type"] == "savedmodel_dir":
        target_dir = get_model_path(key)
        if not os.path.isdir(target_dir):
            return "not_downloaded"
        if not _dir_files_present(info, target_dir):
            return "not_downloaded"
        if not runtime_available(key):
            return "dependency_missing"
        return "ready"
    path = get_model_path(key)
    if not os.path.isfile(path):
        return "not_downloaded"
    size = os.path.getsize(path)
    expected = info.get("expected_bytes")
    if expected and abs(size - expected) > max(1, expected * 0.01):
        return "size_mismatch"
    if not runtime_available(key):
        return "dependency_missing"
    return "ready"


def get_all_statuses():
    return {key: get_model_status(key) for key in MODELS}


def models_by_role(role=None, visible_only=False):
    """Return registry entries filtered by role and visibility."""
    return {
        key: info
        for key, info in MODELS.items()
        if (role is None or info.get("role") == role)
        and (not visible_only or info.get("visible", True))
    }


def models_by_protein(visible_only=False):
    """Return ordered {protein: [model keys]} groups, preserving registry order."""
    grouped = {}
    for key, info in MODELS.items():
        if visible_only and not info.get("visible", True):
            continue
        protein = info.get("protein") or "other"
        grouped.setdefault(protein, []).append(key)
    return grouped


def runtime_available(key):
    """Return True when the optional runtime for a registered model is present."""
    runtime = (MODELS.get(key) or {}).get("runtime", "")
    modules = {
        "numpy": ("numpy",),
        "numpy_h5py": ("numpy", "h5py"),
        "pytorch": ("torch",),
        "tensorflow": ("tensorflow",),
        "web_api": (),
    }
    for module in modules.get(runtime, ()):
        if importlib.util.find_spec(module) is None:
            return False
    return True


def _model_urls(info):
    """Return direct URL first, then a GitHub proxy fallback when relevant."""
    urls = [info["url"]]
    if info["url"].startswith(RAW_GITHUB_PREFIX):
        urls.append(GITHUB_PROXY_PREFIX + info["url"])
    return urls


def _hf_space_resolve_base(info):
    """Return the hf-mirror resolve base for a Hugging Face space entry."""
    source = info.get("source") or {}
    owner = source.get("owner") or ""
    repo = source.get("repo") or ""
    branch = source.get("branch") or "main"
    if not owner or not repo:
        raise RuntimeError("%s is missing its Hugging Face source" % info.get("name"))
    return "%sspaces/%s/%s/resolve/%s" % (HF_MIRROR_PREFIX, owner, repo, branch)


def _download_model_dir(key, info, progress_callback, status_callback):
    """Download every registered file of a directory-backed model.

    This uses the Hugging Face *resolve* endpoint through the domestic mirror
    ``hf-mirror.com`` (which follows redirects to an object store) instead of
    ``git clone`` / ``git lfs pull``, so the mirror's DNS/routing limitations
    that break the normal LFS backend do not apply.
    """
    target_dir = get_model_path(key)
    os.makedirs(target_dir, exist_ok=True)
    base = _hf_space_resolve_base(info)
    files = info.get("files") or []
    lock_path = os.path.join(target_dir, ".download.lock")
    _clear_stale_lock(lock_path)

    total_bytes = sum(item.get("expected_bytes") or 0 for item in files)
    downloaded = 0

    try:
        with open(lock_path, "w", encoding="utf-8") as lock:
            lock.write(str(os.getpid()))

        for item in files:
            rel = item["path"]
            expected = item.get("expected_bytes")
            dest = os.path.join(target_dir, *rel.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)

            if os.path.isfile(dest) and expected and abs(
                    os.path.getsize(dest) - expected) <= max(1, expected * 0.01):
                downloaded += os.path.getsize(dest)
                continue

            url = "%s/%s" % (base.rstrip("/"), rel)
            temp = dest + ".part"
            offset = downloaded

            def progress(done, total):
                if progress_callback:
                    progress_callback(offset + done,
                                      total_bytes or (offset + total))

            def status(state, done, total):
                if status_callback:
                    status_callback(state, offset + done,
                                    total_bytes or (offset + total))

            _download_from_url(url, temp, expected, progress, status)
            if expected and abs(os.path.getsize(temp) - expected) > max(
                    1, expected * 0.01):
                raise RuntimeError(
                    "Downloaded size for %s does not match expected %d"
                    % (rel, expected))
            if os.path.exists(dest):
                os.remove(dest)
            os.replace(temp, dest)
            downloaded += os.path.getsize(dest)

        if status_callback:
            status_callback("done", downloaded, total_bytes or downloaded)
        return target_dir
    finally:
        if os.path.exists(lock_path):
            try:
                os.remove(lock_path)
            except OSError:
                pass

def _process_is_running(pid):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False

    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "PID eq %d" % pid, "/NH"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return str(pid) in result.stdout
        except Exception:
            return True

    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except (PermissionError, OSError):
        return True


def _clear_stale_lock(lock_path):
    """Remove an abandoned lock without blocking retries for an hour."""
    if not os.path.exists(lock_path):
        return
    try:
        with open(lock_path, "r", encoding="utf-8") as lock:
            pid = lock.read().strip()
        if pid and _process_is_running(pid):
            raise RuntimeError("Another download for this model is already running")
        if time.time() - os.path.getmtime(lock_path) > 120:
            os.remove(lock_path)
            return
        raise RuntimeError("Another download for this model is already running")
    except FileNotFoundError:
        pass


def _download_from_url(url, temp_path, expected, progress_callback, status_callback):
    """Download one URL to temp_path, using urllib then curl."""
    resume = os.path.getsize(temp_path) if os.path.isfile(temp_path) else 0
    if status_callback:
        status_callback("connecting", resume, expected or 0)

    last_error = None
    for _ in range(2):
        try:
            headers = {"User-Agent": "Mozilla/5.0 Codex-Model-Downloader/1.0"}
            if resume:
                headers["Range"] = "bytes=%d-" % resume
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=20) as response:
                if response.status == 206:
                    total = expected
                    if not total:
                        content_range = response.headers.get("Content-Range") or ""
                        try:
                            total = int(content_range.rsplit("/", 1)[-1])
                        except (ValueError, IndexError):
                            total = resume + int(response.headers.get("Content-Length") or 0)
                    mode = "ab"
                else:
                    total = expected or int(response.headers.get("Content-Length") or 0)
                    resume = 0
                    mode = "wb"
                downloaded = resume
                if status_callback:
                    status_callback("downloading", downloaded, total)
                with open(temp_path, mode) as out:
                    while True:
                        if expected and downloaded >= expected:
                            break
                        chunk = response.read(1024 * 256)
                        if not chunk:
                            break
                        out.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total:
                            progress_callback(downloaded, total)
                        if status_callback:
                            status_callback("downloading", downloaded, total)
            return
        except Exception as exc:
            last_error = exc
            part_size = os.path.getsize(temp_path) if os.path.isfile(temp_path) else 0
            if status_callback:
                status_callback("retrying", part_size, expected or 0)
            time.sleep(1.5)

    curl = shutil.which("curl")
    if curl is None:
        raise RuntimeError(
            "Download failed: %s and no curl/wget fallback is available" % last_error
        )
    resume_arg = ["-C", "-"] if os.path.isfile(temp_path) else []
    if status_callback:
        status_callback("curl", resume, expected or 0)
    result = subprocess.run(
        [curl, "-L", "--fail", "--retry", "3", "--retry-delay", "2",
         "--connect-timeout", "15", "--max-time", "600",
         *resume_arg, "-o", temp_path, url],
        capture_output=True,
        text=True,
        timeout=700,
    )
    if result.returncode != 0:
        raise RuntimeError("curl download failed: %s" % result.stderr)


def download_model(key, progress_callback=None, status_callback=None):
    info = MODELS[key]
    if info["type"] == "web":
        raise ValueError("%s is an online service and does not need downloading" % key)
    if info["type"] == "external":
        raise ValueError("%s is an external model repository and requires manual setup" % key)
    if info["type"] == "savedmodel_dir":
        return _download_model_dir(key, info, progress_callback, status_callback)

    path = get_model_path(key)
    os.makedirs(MODEL_DIR, exist_ok=True)
    temp_path = path + ".part"
    lock_path = path + ".lock"
    expected = info.get("expected_bytes")

    if get_model_status(key) == "ready":
        if status_callback:
            status_callback("done", os.path.getsize(path), expected or os.path.getsize(path))
        return path

    if os.path.isfile(temp_path) and expected:
        part_size = os.path.getsize(temp_path)
        if part_size >= expected:
            os.replace(temp_path, path)
            if status_callback:
                status_callback("done", part_size, expected)
            return path

    _clear_stale_lock(lock_path)

    try:
        with open(lock_path, "w", encoding="utf-8") as lock:
            lock.write(str(os.getpid()))
    except OSError as exc:
        raise RuntimeError("Cannot create download lock: %s" % exc)

    try:
        last_error = None
        for index, url in enumerate(_model_urls(info)):
            if index > 0 and status_callback:
                status_callback("mirror", 0, expected or 0)
            try:
                _download_from_url(
                    url,
                    temp_path,
                    expected,
                    progress_callback,
                    status_callback,
                )
                break
            except Exception as exc:
                last_error = exc
                if status_callback:
                    status_callback("retrying", 0, expected or 0)
        else:
            raise last_error if last_error else RuntimeError("Download failed")

        final_size = os.path.getsize(temp_path)
        if expected and abs(final_size - expected) > max(1, expected * 0.01):
            raise RuntimeError(
                "Downloaded size %d does not match expected %d" % (final_size, expected))
        if os.path.exists(path):
            os.remove(path)
        os.replace(temp_path, path)
        if status_callback:
            status_callback("done", final_size, expected or final_size)
        return path
    finally:
        if os.path.exists(lock_path):
            try:
                os.remove(lock_path)
            except OSError:
                pass


def delete_model(key):
    info = MODELS[key]
    if info["type"] in ("web", "external"):
        return
    if info["type"] == "savedmodel_dir":
        target = get_model_path(key)
        if os.path.isdir(target):
            shutil.rmtree(target, ignore_errors=True)
        return
    path = get_model_path(key)
    for suffix in ("", ".part", ".lock"):
        target = path + suffix if suffix else path
        if os.path.isfile(target):
            try:
                os.remove(target)
            except OSError:
                pass


def model_keys():
    return list(MODELS.keys())
