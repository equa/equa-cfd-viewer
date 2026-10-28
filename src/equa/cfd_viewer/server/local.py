"""Local mode: one user's viewer on their own machine.

The server listens on loopback only, and still has to keep out other users of
the same machine and web pages that send requests to ``localhost``. Each launch
makes a token; the browser opens ``/?t=<token>``, which the server swaps for a
cookie named for the port, and every other request needs that cookie. A second
process -- the next launch, handing over its folders -- sends the token in a
header instead. Requests for any other ``Host`` are refused, which closes off
DNS rebinding (openspec local-desktop-viewer, design D1).

One launch per user: the port and token go into a per-user instance file, and
a later launch that finds a live viewer there hands it its folders and exits.
The folder browser, recent folders and quitting are local mode's own endpoints
(D2, D3).
"""

import hmac
import json
import os
import secrets
import socket
import urllib.request
from pathlib import Path

from aiohttp import web

from .paths import user_dir
from .sources import is_case

TOKEN_HEADER = "X-Cfd-Viewer-Token"
# Answers without the token, so a later launch can check who holds the port
# before it sends the token there.
INSTANCE_PATH = "/api/instance"
LOOPBACK_HOSTS = ("127.0.0.1", "localhost")


def bind_loopback(port=0):
    """A listening socket on 127.0.0.1; port 0 lets the system pick a free one.

    Bound and listening before the server starts, so the port is known for the
    URL and the ``Host`` check, and a browser opened right away is queued
    rather than refused.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):  # Windows: no one else may bind it too
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    sock.bind(("127.0.0.1", port))
    sock.listen(128)
    return sock


class LocalSession:
    """The token, cookie and hosts of one local launch."""

    def __init__(self, port, token=None, recent=None):
        self.port = port
        self.recent = recent or RecentFolders(settings_path())
        self.token = token or secrets.token_urlsafe(32)  # 256 bits
        self.cookie = f"cfdv_{port}"
        self.hosts = {f"{host}:{port}" for host in LOOPBACK_HOSTS}

    def url(self):
        return f"http://127.0.0.1:{self.port}/?t={self.token}"

    def _valid(self, value):
        return value is not None and hmac.compare_digest(value, self.token)

    def proof(self, nonce):
        return instance_proof(self.token, nonce)

    @web.middleware
    async def guard(self, request, handler):
        if request.host not in self.hosts:
            raise web.HTTPForbidden(text="wrong host")
        if request.path == INSTANCE_PATH:
            return await handler(request)
        if self._valid(request.headers.get(TOKEN_HEADER)):
            return await handler(request)
        if self._valid(request.query.get("t")):
            rest = [(k, v) for k, v in request.query.items() if k != "t"]
            response = web.HTTPFound(request.rel_url.with_query(rest))
            response.set_cookie(self.cookie, self.token, httponly=True,
                                samesite="Strict", path="/")
            return response
        if self._valid(request.cookies.get(self.cookie)):
            return await handler(request)
        raise web.HTTPForbidden(text="open the viewer from the link it printed or opened")


# -- per-user files ------------------------------------------------------------


def instance_path():
    """Where a running local viewer records its port and token."""
    return user_dir("LOCALAPPDATA", "XDG_STATE_HOME", ".local/state") / "instance.json"


def settings_path():
    """The user's settings, recent folders among them."""
    return user_dir("APPDATA", "XDG_CONFIG_HOME", ".config") / "settings.json"


def claim_instance(path, session):
    """Record *session* in the instance file; False when another launch holds it.

    Created exclusively, so two launches at the same moment cannot both start a
    server, and readable by this user only: it holds the token.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"port": session.port, "token": session.token, "pid": os.getpid()}, f)
    return True


def read_instance(path):
    """``(port, token)`` from the instance file, or None."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return int(data["port"]), str(data["token"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def release_instance(path, session):
    """Remove the instance file, if it is still this session's."""
    if read_instance(path) == (session.port, session.token):
        path.unlink(missing_ok=True)


def _call(port, token, path, body=None, timeout=2):
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", method="POST" if body is not None else "GET",
        data=None if body is None else json.dumps(body).encode(),
        headers={TOKEN_HEADER: token, "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, json.loads(response.read() or b"null")


def instance_proof(token, nonce):
    """What only the holder of *token* can answer to *nonce*."""
    return hmac.new(token.encode(), f"cfd-viewer instance {nonce}".encode(),
                    "sha256").hexdigest()


def is_live(port, token):
    """True when the local viewer holding *token* answers on *port*.

    Answering is not enough: whatever else took the port must not receive the
    token or the user's folders. So the token is not sent; the instance proves
    it holds it by answering a fresh nonce.
    """
    nonce = secrets.token_hex(16)
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{port}{INSTANCE_PATH}?nonce={nonce}", timeout=2) as response:
            answer = json.loads(response.read())
    except (OSError, ValueError):
        return False
    proof = answer.get("proof") if isinstance(answer, dict) else None
    return isinstance(proof, str) and hmac.compare_digest(proof, instance_proof(token, nonce))


def hand_over(port, token, folders):
    """Add *folders* to the running instance on *port*."""
    for folder in folders:
        _call(port, token, "/api/folders", {"path": str(folder)}, timeout=30)


class RecentFolders:
    """The folders the user added, most recent first, kept across launches."""

    LIMIT = 10

    def __init__(self, path):
        self.path = path

    def _read(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def list(self):
        folders = self._read().get("recentFolders", [])
        return [f for f in folders if isinstance(f, str) and Path(f).is_dir()]

    def add(self, folder):
        folder = str(folder)
        data = self._read()
        data["recentFolders"] = [folder, *[f for f in self.list() if f != folder]][:self.LIMIT]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# -- the folder browser ---------------------------------------------------------


def _has_zip(directory):
    try:
        return any(p.suffix.lower() == ".zip" for p in directory.iterdir())
    except OSError:
        return False


def _has_case_below(directory):
    """A shallow mark: a case among the direct subdirectories, or a zip in the
    ``cfd`` one, or in *directory* when it is a ``cfd`` directory itself. A walk
    to the scan depth for every listed entry takes seconds on a home or network
    drive, and no zip is opened: a project of bare cases is marked too
    (openspec ice-project-zips, D7)."""
    if directory.name.lower() == "cfd" and _has_zip(directory):
        return True
    try:
        children = [child for child in directory.iterdir() if child.is_dir()]
    except OSError:
        return False
    return any(is_case(child) or (child.name.lower() == "cfd" and _has_zip(child))
               for child in children)


def browse(path):
    """``/api/folders``: drives (or ``/`` and home) for no path, else subdirectories."""
    if not path:
        if hasattr(os, "listdrives"):  # Windows, mapped network drives included
            tops = [Path(d) for d in os.listdrives()]
        else:
            tops = [Path.home(), Path("/")]
        return {"path": None, "parent": None,
                "entries": [{"name": str(p), "path": str(p), "isCase": False,
                             "hasCases": False} for p in tops]}
    directory = Path(path).resolve()
    children = sorted((p for p in directory.iterdir()
                       if p.is_dir() and not p.name.startswith(".")),
                      key=lambda p: p.name.lower())
    parent = directory.parent if directory.parent != directory else None
    return {
        "path": str(directory),
        "parent": None if parent is None else str(parent),
        "entries": [{"name": p.name, "path": str(p), "isCase": is_case(p),
                     "hasCases": _has_case_below(p)} for p in children],
    }
