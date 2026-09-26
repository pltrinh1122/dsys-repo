"""Containment audit hook — placed at <scratch>/pkg/sitecustomize.py.

DO NOT IMPORT DIRECTLY. The launcher (author_contain.py) copies this file
into the per-run scratch tree at ``<scratch>/pkg/sitecustomize.py``. The
launcher sets ``PYTHONPATH=<scratch>/pkg``; PYTHONPATH precedes the stdlib
on the interpreter's startup path, so ``site`` imports THIS file (not the
stdlib's own sitecustomize) and the audit hook is installed before any
contained code runs. (A scratch-root copy would NOT work: for ``python
-m``, cwd reaches sys.path only after site has already imported
sitecustomize.)

It installs a :func:`sys.addaudithook` that REFUSES, with reasons:
  - filesystem writes outside the scratch dir
    (open-for-write, mkdir/makedirs, unlink/remove/rmdir,
     rename/replace, symlink/link, truncate, mkfifo/mknod)
  - subprocess spawning
  - socket use (network)

Reads anywhere are allowed: the interpreter itself reads outside the
scratch dir (stdlib, the venv, /proc, locale data). Refusing reads would
break the interpreter; the threat model is writes/effects, not reads.

This is a refusal mechanism for accidental escapes by AUTHORED code
(gated by the factory verifier, authored by the verified wright) — it is
NOT an OS security sandbox. A deliberately adversarial process running
as the same user could evade an interpreter-level hook. Sandboxing
adversarial code is an explicit non-goal (that would be Docker, declined
in the /pb-decide, DR-CMD-086). See doc/author-agent-containment-spec.md.
"""

import os
import sys

_SCRATCH = os.path.realpath(os.environ.get("AUTHOR_CONTAIN_SCRATCH", ""))


class ContainmentRefusal(PermissionError):
    """Raised when contained code attempts an effect outside the scratch dir."""


def _outside(path):
    """True when path is outside the scratch dir (resolved, symlink-safe)."""
    if not path or not _SCRATCH:
        return False
    rp = os.path.realpath(path)
    return rp != _SCRATCH and not rp.startswith(_SCRATCH + os.sep)


_WRITE_EVENTS = {
    "os.mkdir", "os.makedirs", "os.removedirs",
    "os.remove", "os.unlink", "os.rmdir",
    "os.rename", "os.renames", "os.replace",
    "os.symlink", "os.link", "os.truncate",
    "os.mkfifo", "os.mknod",
}

_SUBPROCESS_EVENTS = {
    "subprocess.Popen",
    "os.system",
    "os.posix_spawn", "os.posix_spawnp",
    "os.spawnl", "os.spawnle", "os.spawnlp", "os.spawnlpe",
    "os.spawnv", "os.spawnve", "os.spawnvp", "os.spawnvpe",
    "os.fork", "os.forkpty",
    "os.execv", "os.execve", "os.execl", "os.execle",
    "os.execlp", "os.execlpe", "os.execvp", "os.execvpe",
}

_NETWORK_EVENTS = {
    "socket.getaddrinfo", "socket.getnameinfo",
    "socket.socket", "socket.bind", "socket.connect",
}


def _open_is_write(mode, flags):
    if isinstance(mode, str) and any(c in mode for c in "wax+"):
        return True
    try:
        f = int(flags)
    except (TypeError, ValueError):
        return False
    return bool(f & (os.O_WRONLY | os.O_RDWR | os.O_CREAT
                     | os.O_TRUNC | os.O_APPEND))


def _first_path(args):
    for a in args:
        if isinstance(a, (str, bytes, os.PathLike)):
            s = os.fspath(a)
            if isinstance(s, bytes):
                s = s.decode("utf-8", "replace")
            return s
    return None


def _hook(event, args):
    if event in _SUBPROCESS_EVENTS:
        raise ContainmentRefusal(
            f"contained process may not spawn subprocesses ({event})")
    if event in _NETWORK_EVENTS:
        raise ContainmentRefusal(
            f"contained process may not use the network ({event})")
    if event == "open":
        path = args[0] if args else None
        if isinstance(path, int):
            return  # fd-relative; the fd was opened under these same rules
        mode = args[1] if len(args) > 1 else ""
        flags = args[2] if len(args) > 2 else 0
        s = _first_path((path,))
        if s is not None and _open_is_write(mode, flags) and _outside(s):
            raise ContainmentRefusal(
                f"write outside scratch refused: {s!r}")
        return
    if event in _WRITE_EVENTS:
        s = _first_path(args)
        if s is not None and _outside(s):
            raise ContainmentRefusal(
                f"{event} outside scratch refused: {s!r}")


sys.addaudithook(_hook)
