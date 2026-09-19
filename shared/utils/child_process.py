#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Keep external child processes from outliving the process that started them.

The native off-target engine can run for days and hold hundreds of gigabytes,
so a parent that dies (crash, closed GUI, SIGTERM) must not leave the engine
running. Children are started in their own process group, registered here, and
torn down by ``terminate_process_tree`` when the caller unwinds, when the
interpreter exits, or when the parent is signalled.
"""

from __future__ import annotations

import atexit
import os
import signal
import subprocess
import threading


# How long a child may take to honour SIGTERM before it is SIGKILLed.
TERMINATE_GRACE_S = 5.0

# Set PROGRAMFILE_CHILD_PDEATHSIG=0 to skip the Linux parent-death signal.
PDEATHSIG_ENV = "PROGRAMFILE_CHILD_PDEATHSIG"

# PR_SET_PDEATHSIG: the kernel signals the child when its parent thread dies.
_PR_SET_PDEATHSIG = 1

_ACTIVE = set()
_ACTIVE_LOCK = threading.Lock()
_ATEXIT_INSTALLED = False
_SIGNALS_INSTALLED = False

# Resolve libc.prctl at import time: ``preexec_fn`` runs after ``fork()``,
# where importing modules is not safe in a threaded process.
try:
    import ctypes

    _LIBC = ctypes.CDLL(None, use_errno=True)
    _PRCTL = _LIBC.prctl
except Exception:  # pragma: no cover - platform dependent
    _LIBC = None
    _PRCTL = None


def pdeathsig_enabled():
    """Return whether Linux children should die with their parent."""
    value = (os.environ.get(PDEATHSIG_ENV) or "1").strip().lower()
    return value in ("1", "true", "on", "yes", "enabled")


def _preexec_pdeathsig():
    """Child-side hook: die when the parent thread that forked us dies."""
    if _PRCTL is None:
        return
    try:
        _PRCTL(_PR_SET_PDEATHSIG, signal.SIGKILL)
    except Exception:  # pragma: no cover - best effort only
        pass


def popen_kwargs(pdeathsig=True):
    """Return ``Popen`` keyword arguments that isolate the child process."""
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    kwargs = {"start_new_session": True}
    if pdeathsig and _PRCTL is not None and pdeathsig_enabled():
        kwargs["preexec_fn"] = _preexec_pdeathsig
    return kwargs


def terminate_process_tree(proc, grace_s=TERMINATE_GRACE_S):
    """SIGTERM, then SIGKILL, the child and everything in its group."""
    if proc is None:
        return
    try:
        if proc.poll() is not None:
            return
    except Exception:
        return
    if os.name == "nt":
        _terminate_single(proc, grace_s)
        return
    try:
        pgid = os.getpgid(proc.pid)
    except OSError:
        pgid = None
    for signum in (signal.SIGTERM, signal.SIGKILL):
        if proc.poll() is not None:
            return
        try:
            if pgid is None:
                proc.send_signal(signum)
            else:
                os.killpg(pgid, signum)
        except OSError:
            return
        if _wait_briefly(proc, grace_s):
            return


def _terminate_single(proc, grace_s):
    try:
        proc.terminate()
    except OSError:
        return
    if _wait_briefly(proc, grace_s):
        return
    try:
        proc.kill()
    except OSError:
        return
    _wait_briefly(proc, grace_s)


def _wait_briefly(proc, grace_s):
    try:
        proc.wait(timeout=grace_s)
        return True
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return True


def register_child(proc):
    """Track ``proc`` so the exit and signal handlers can reap it."""
    _install_handlers()
    with _ACTIVE_LOCK:
        _ACTIVE.add(proc)


def unregister_child(proc):
    with _ACTIVE_LOCK:
        _ACTIVE.discard(proc)


def active_children():
    """Return the registered children that are still running."""
    with _ACTIVE_LOCK:
        processes = list(_ACTIVE)
    running = []
    for proc in processes:
        try:
            if proc.poll() is None:
                running.append(proc)
        except Exception:
            continue
    return running


def reap_children():
    """Terminate every registered child that is still running."""
    for proc in active_children():
        terminate_process_tree(proc)


def _install_handlers():
    global _ATEXIT_INSTALLED, _SIGNALS_INSTALLED
    if not _ATEXIT_INSTALLED:
        _ATEXIT_INSTALLED = True
        atexit.register(reap_children)
    if _SIGNALS_INSTALLED or os.name != "posix":
        return
    if threading.current_thread() is not threading.main_thread():
        return
    _SIGNALS_INSTALLED = True
    for signum in (signal.SIGTERM, signal.SIGINT):
        try:
            previous = signal.getsignal(signum)
        except (ValueError, OSError):
            continue
        if previous is not signal.SIG_DFL:
            continue
        try:
            signal.signal(signum, _make_handler(signum))
        except (ValueError, OSError):
            continue


def _make_handler(signum):
    def handler(_signum, _frame):
        reap_children()
        try:
            signal.signal(signum, signal.SIG_DFL)
            os.kill(os.getpid(), signum)
        except (ValueError, OSError):
            pass

    return handler
