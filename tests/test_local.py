"""Local mode: loopback only, and only the launching user's browser gets in
(openspec local-desktop-viewer, local-desktop-run)."""

import asyncio
import http.cookiejar
import http.server
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from aiohttp.test_utils import TestClient, TestServer

from equa.cfd_viewer.server.app import make_app
from equa.cfd_viewer.server.local import TOKEN_HEADER, LocalSession, RecentFolders
from equa.cfd_viewer.server.sources import DirectorySource

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "data" / "hotRoom"
PORT = 50123  # what the session believes it listens on; the Host header carries it


def _local(*requests, roots=(DEMO,), recent=None):
    """[(status, headers, body), ...] for requests against a local-mode app.

    Each request is ``(path, headers)``, or ``(path, headers, json_body)`` for a
    POST; the client keeps cookies between them, as a browser does.
    """
    session = LocalSession(PORT, token="secret-token", recent=recent or RecentFolders(
        Path(tempfile.mkdtemp(prefix="cfdv-")) / "settings.json"))

    async def run():
        app = make_app(DirectorySource(list(roots)), mode="local", local=session)
        async with TestClient(TestServer(app)) as client:
            out = []
            for path, headers, *body in requests:
                headers = {"Host": f"127.0.0.1:{PORT}", **headers}
                if body:
                    response = await client.post(path, headers=headers, json=body[0])
                else:
                    response = await client.get(path, headers=headers, allow_redirects=False)
                out.append((response.status, response.headers, await response.text()))
            return out

    return asyncio.run(run())


TOKEN = {TOKEN_HEADER: "secret-token"}


def test_no_token_is_403():
    [(status, _, body)] = _local(("/api/cases", {}))
    assert status == 403
    assert "hotRoom" not in body


def test_token_becomes_a_cookie_and_redirects():
    (status, headers, _), (after, _, body) = _local(
        ("/?t=secret-token&case=hotRoom", {}), ("/api/cases", {}))
    assert status == 302
    assert headers["Location"] == "/?case=hotRoom"
    cookie = headers["Set-Cookie"]
    assert cookie.startswith(f"cfdv_{PORT}=secret-token")
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie
    assert after == 200 and "hotRoom" in body


def test_wrong_token_is_403():
    [(status, headers, _)] = _local(("/?t=guess", {}))
    assert status == 403
    assert "Set-Cookie" not in headers


def test_wrong_host_is_403_even_with_the_cookie():
    _, (status, _, _) = _local(
        ("/?t=secret-token", {}),
        ("/api/cases", {"Host": f"attacker.example:{PORT}"}))
    assert status == 403


def test_localhost_is_a_valid_host():
    [(status, _, _)] = _local(("/api/cases", {"Host": f"localhost:{PORT}",
                                              TOKEN_HEADER: "secret-token"}))
    assert status == 200


def test_header_token_for_another_process():
    [(status, _, body)] = _local(("/api/config", {TOKEN_HEADER: "secret-token"}))
    assert status == 200
    assert '"mode": "local"' in body and '"canAddFolders": true' in body


def test_server_mode_has_no_guard():
    async def run():
        async with TestClient(TestServer(make_app(DirectorySource([DEMO])))) as client:
            response = await client.get("/api/cases",
                                        headers={"Host": "attacker.example"})
            return response.status

    assert asyncio.run(run()) == 200


def test_local_mode_needs_a_session():
    with pytest.raises(ValueError):
        make_app(DirectorySource([DEMO]), mode="local")


def _external_ip():
    """This machine's address on a non-loopback interface, or None."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect(("10.255.255.255", 1))  # no packet is sent
            ip = probe.getsockname()[0]
        except OSError:
            return None
    return None if ip.startswith("127.") else ip


def _launch(tmp_path, *args, env=None):
    """A local-mode viewer process whose per-user files live under *tmp_path*."""
    return subprocess.Popen(
        [sys.executable, "-m", "equa.cfd_viewer", "--mode", "local", "--no-browser", *args],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, cwd=ROOT,
        env={"PATH": "", "HOME": str(tmp_path), "XDG_STATE_HOME": str(tmp_path / "state"),
             "XDG_CONFIG_HOME": str(tmp_path / "config"), **(env or {})})


def _instance(tmp_path):
    return tmp_path / "state" / "equa" / "cfd-viewer" / "instance.json"


def _api(port, path, body=None, token=None):
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", method="POST" if body is not None else "GET",
        data=None if body is None else json.dumps(body).encode(),
        headers={TOKEN_HEADER: token or "", "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())


def _wait_up(port, token):
    for _ in range(150):
        try:
            return _api(port, "/api/config", token=token)
        except OSError:
            time.sleep(0.1)
    raise AssertionError(f"no viewer on port {port}")


def _stop(proc):
    proc.terminate()
    proc.wait(timeout=10)


def test_launch_binds_loopback_only_and_prints_the_url(tmp_path):
    proc = _launch(tmp_path, str(DEMO), env={"PORT": "5003", "CASE_ROOTS": "/nowhere"})
    try:
        url = proc.stdout.readline().strip()
        parts = urlsplit(url)
        assert parts.hostname == "127.0.0.1" and parts.query.startswith("t=")
        assert parts.port != 5003  # $PORT is ignored
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        for _ in range(100):
            try:
                with opener.open(url, timeout=5) as response:
                    assert response.status == 200
                break
            except urllib.error.URLError:
                time.sleep(0.1)
        with opener.open(f"http://127.0.0.1:{parts.port}/api/cases", timeout=5) as response:
            assert b"hotRoom" in response.read()  # $CASE_ROOTS is ignored too
        ip = _external_ip()
        if ip:
            with pytest.raises(OSError):
                socket.create_connection((ip, parts.port), timeout=2).close()
    finally:
        _stop(proc)


def test_second_launch_hands_over_and_starts_no_server(tmp_path):
    other = tmp_path / "other"
    (other / "run2" / "system").mkdir(parents=True)
    (other / "run2" / "system" / "controlDict").write_text("")
    first = _launch(tmp_path, str(DEMO))
    try:
        url = first.stdout.readline().strip()
        port, token = urlsplit(url).port, urlsplit(url).query[2:]
        _wait_up(port, token)
        second = _launch(tmp_path, str(other))
        out, _ = second.communicate(timeout=60)
        assert second.returncode == 0
        assert urlsplit(out.strip()).port == port  # the running one, no new server
        names = _api(port, "/api/cases", token=token)["cases"]
        assert names == ["hotRoom", "run2"]
    finally:
        _stop(first)


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _write_instance(tmp_path, port):
    path = _instance(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"port": port, "token": "old-token", "pid": 1}))
    os.utime(path, (0, 0))  # old: no grace for a viewer still starting


def test_stale_instance_file_is_replaced(tmp_path):
    dead = _free_port()
    _write_instance(tmp_path, dead)
    proc = _launch(tmp_path, str(DEMO))
    try:
        port = urlsplit(proc.stdout.readline().strip()).port
        assert port != dead
        assert json.loads(_instance(tmp_path).read_text())["port"] == port
    finally:
        _stop(proc)


def test_no_token_or_folder_goes_to_another_program_on_the_port(tmp_path):
    seen = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 -- http.server's naming
            seen.append(("GET", self.path))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"mode": "local"}')

        def do_POST(self):  # noqa: N802
            seen.append(("POST", self.path))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    impostor = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=impostor.serve_forever, daemon=True).start()
    _write_instance(tmp_path, impostor.server_address[1])
    proc = _launch(tmp_path, str(DEMO))
    try:
        port = urlsplit(proc.stdout.readline().strip()).port
        assert port != impostor.server_address[1]
        assert not any(method == "POST" for method, _ in seen)
        assert not any("old-token" in path for _, path in seen)
    finally:
        _stop(proc)
        impostor.shutdown()


def test_quit_stops_the_server_and_removes_the_instance_file(tmp_path):
    proc = _launch(tmp_path, str(DEMO))
    url = proc.stdout.readline().strip()
    port, token = urlsplit(url).port, urlsplit(url).query[2:]
    _wait_up(port, token)
    assert _instance(tmp_path).exists()
    assert _api(port, "/api/quit", body={}, token=token) == {"stopping": True}
    assert proc.wait(timeout=15) == 0
    assert not _instance(tmp_path).exists()


def test_network_host_is_refused():
    result = subprocess.run(
        [sys.executable, "-m", "equa.cfd_viewer", "--mode", "local", "--no-browser",
         "--host", "0.0.0.0", str(DEMO)],
        capture_output=True, text=True, cwd=ROOT, timeout=60)
    assert result.returncode == 2
    assert "127.0.0.1 only" in result.stderr


def test_instance_proof_needs_no_token_and_reveals_none():
    [(status, _, body)] = _local(("/api/instance?nonce=0123456789abcdef", {}))
    assert status == 200
    proof = json.loads(body)["proof"]
    assert proof == LocalSession(PORT, token="secret-token",
                                 recent=RecentFolders(Path("x"))).proof("0123456789abcdef")
    assert "secret-token" not in body


def test_browse_marks_cases_and_folders_with_cases(tmp_path):
    (tmp_path / "proj" / "run1" / "system").mkdir(parents=True)
    (tmp_path / "proj" / "run1" / "system" / "controlDict").write_text("")
    (tmp_path / "empty").mkdir()
    (tmp_path / ".hidden").mkdir()
    [(status, _, body)] = _local((f"/api/folders?path={tmp_path}", TOKEN))
    assert status == 200
    listing = json.loads(body)
    marks = {e["name"]: (e["isCase"], e["hasCases"]) for e in listing["entries"]}
    assert marks == {"empty": (False, False), "proj": (False, True)}
    [(_, _, body)] = _local((f"/api/folders?path={tmp_path / 'proj'}", TOKEN))
    assert json.loads(body)["entries"][0]["isCase"] is True


def test_browse_without_a_path_lists_the_tops():
    [(status, _, body)] = _local(("/api/folders", TOKEN))
    assert status == 200 and json.loads(body)["entries"]


def test_add_folder_lists_its_cases_and_remembers_it(tmp_path):
    (tmp_path / "cases" / "run1" / "system").mkdir(parents=True)
    (tmp_path / "cases" / "run1" / "system" / "controlDict").write_text("")
    recent = RecentFolders(tmp_path / "settings.json")
    folder = str((tmp_path / "cases").resolve())
    (added, _, body), (_, _, cases), (_, _, config) = _local(
        ("/api/folders", TOKEN, {"path": folder}), ("/api/cases", TOKEN),
        ("/api/config", TOKEN), roots=(), recent=recent)
    assert added == 200 and json.loads(body) == {"added": True, "path": folder}
    assert json.loads(cases)["cases"] == ["run1"]
    assert json.loads(config)["recentFolders"] == [folder]


def test_adding_a_missing_folder_is_404(tmp_path):
    [(status, _, _)] = _local(("/api/folders", TOKEN, {"path": str(tmp_path / "gone")}))
    assert status == 404


def test_recent_folders_keep_ten_and_drop_missing(tmp_path):
    recent = RecentFolders(tmp_path / "settings.json")
    folders = []
    for i in range(12):
        folders.append(tmp_path / f"f{i}")
        folders[-1].mkdir()
        recent.add(folders[-1])
    assert recent.list() == [str(f) for f in reversed(folders)][:10]
    folders[11].rmdir()
    assert recent.list()[0] == str(folders[10])
    recent.add(folders[5])
    assert recent.list()[0] == str(folders[5]) and len(recent.list()) == 9


def test_local_endpoints_are_404_in_server_mode():
    async def run():
        async with TestClient(TestServer(make_app(DirectorySource([DEMO])))) as client:
            return [(await client.get("/api/folders")).status,
                    (await client.post("/api/folders", json={"path": "/"})).status,
                    (await client.post("/api/quit", json={})).status]

    assert asyncio.run(run()) == [404, 404, 404]
