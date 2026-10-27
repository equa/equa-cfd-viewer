#!/usr/bin/env python3
"""Smoke test of the frozen Windows bundle (openspec local-desktop-viewer, D6).

    python tests/check_frozen.py dist/cfd-viewer/cfd-viewer.exe <cases-root> \
        --version 1.0.0-beta.5 --zip cfd-viewer-1.0.0-beta.5-win64.zip --summary FILE

Starts the executable in local mode on a cases root, as a user would with a
folder dropped onto it, and checks what the bundle must do: the token flow, the
client, the case list, a full scene of every case, the version it reports, that
nothing is written into the cases, and that Quit stops it. The zip size and the
time from launch to first page go into the summary. Runs against an unfrozen
``cfd-viewer`` too, which is how it is tried on Linux.
"""

import argparse
import http.cookiejar
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

EVERY = "boundary,slice,iso,stream,glyph,geometry"


def snapshot(root):
    return {p.relative_to(root).as_posix() for p in root.rglob("*")}


def expected_version(raw):
    """The PEP 440 form the package reports (``1.0.0b5`` for ``1.0.0-beta.5``)."""
    try:
        from packaging.version import Version
    except ImportError:
        return raw
    return str(Version(raw))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("exe", type=Path)
    parser.add_argument("root", type=Path)
    parser.add_argument("--version", help="the version the bundle must report")
    parser.add_argument("--zip", type=Path, help="the zip, for its size")
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()

    rows, failed = [], False

    def check(name, ok, detail=""):
        nonlocal failed
        failed |= not ok
        rows.append((name, "ok" if ok else "FAIL", detail))

    if args.zip:
        rows.append(("zip size", "-", f"{args.zip.stat().st_size / 2**20:.0f} MB"))

    home = Path(tempfile.mkdtemp(prefix="cfdv-frozen-"))
    env = {**os.environ, "LOCALAPPDATA": str(home / "local"), "APPDATA": str(home / "roaming"),
           "XDG_STATE_HOME": str(home / "state"), "XDG_CONFIG_HOME": str(home / "config")}
    before = snapshot(args.root)
    t0 = time.monotonic()
    proc = subprocess.Popen(
        [str(args.exe), "--mode", "local", "--no-browser", str(args.root)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    out = ""
    try:
        url = proc.stdout.readline().strip()
        parts = urlsplit(url)
        check("prints its URL", parts.hostname == "127.0.0.1" and parts.query.startswith("t="),
              url.split("?")[0])
        base = f"http://127.0.0.1:{parts.port}"
        jar = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        bare = urllib.request.build_opener()

        def get(opener, path, headers=None, timeout=300):
            request = urllib.request.Request(base + path, headers=headers or {})
            try:
                with opener.open(request, timeout=timeout) as r:
                    return r.status, r.read()
            except urllib.error.HTTPError as e:
                return e.code, e.read()

        page = None
        while time.monotonic() - t0 < 300 and proc.poll() is None:
            try:
                page = get(jar, url[len(base):], timeout=5)
                break
            except OSError:
                time.sleep(0.2)
        t_page = time.monotonic() - t0
        check("serves the client with the token", page is not None and page[0] == 200
              and b'id="root"' in page[1], f"first page {t_page:.1f} s after launch")
        rows.append(("launch to first page", "-", f"{t_page:.1f} s"))

        check("403 without the token", get(bare, "/api/cases")[0] == 403)
        status, _ = get(jar, "/api/cases", headers={"Host": f"attacker.example:{parts.port}"})
        check("403 for another Host, cookie or not", status == 403)

        status, body = get(jar, "/api/config")
        config = json.loads(body) if status == 200 else {}
        if args.version:
            want = expected_version(args.version)
            check("reports its version", config.get("version") == want,
                  f"{config.get('version')} (expected {want})")
        check("runs in local mode", config.get("mode") == "local", str(config.get("mode")))

        status, body = get(jar, "/api/cases")
        names = json.loads(body)["cases"] if status == 200 else []
        check("lists the cases", len(names) >= 2, ", ".join(names) or f"{status}")
        for name in names:
            status, body = get(jar, f"/api/meta?case={name}")
            meta = json.loads(body) if status == 200 else {}
            check(f"{name}: meta", status == 200,
                  f"times {meta.get('times')}, decomposed {meta.get('decomposed')}")
            t = time.monotonic()
            status, body = get(jar, f"/api/scene?case={name}&field=U&component=magnitude"
                                    f"&parts={EVERY}")
            check(f"{name}: full scene", status == 200 and len(body) > 100_000,
                  f"{len(body) / 1e6:.2f} MB in {time.monotonic() - t:.1f} s")

        request = urllib.request.Request(base + "/api/quit", data=b"{}", method="POST",
                                         headers={"Content-Type": "application/json"})
        with jar.open(request, timeout=30) as r:
            quit_ok = r.status == 200
        check("Quit stops it", quit_ok and proc.wait(timeout=30) == 0)
        written = sorted(snapshot(args.root) - before)
        check("writes nothing into the cases", not written, ", ".join(written[:5]))
    finally:
        if proc.poll() is None:
            proc.kill()
        out = proc.communicate()[0] or ""

    table = ["| Check | Result | Detail |", "|---|---|---|"]
    table += [f"| {n} | {r} | {d} |" for n, r, d in rows]
    text = "\n".join(table) + "\n"
    print(text)
    print("--- viewer output ---")
    print(out[-4000:])
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as f:
            f.write(f"\n**Frozen smoke test** (`{args.exe}`)\n\n{text}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
