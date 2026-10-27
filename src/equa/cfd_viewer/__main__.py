"""cfd-viewer -- browse OpenFOAM results in a web browser.

    cfd-viewer --data ./data --port 5003
    python -m equa.cfd_viewer --data ./data --port 5003
    cfd-viewer --mode local C:\\cases     (your own machine; opens the browser)

VTK extracts server-side (``foamviz/`` + ``server/``); the browser draws with
React and three.js (``web/``).

In server mode every option can also come from the environment, as platform
services are configured (equa-deployment); a command-line option wins over its
variable. Local mode reads none of them: it listens on 127.0.0.1 on a port the
system picks, and shows only the folders given or added.

    CASE_ROOTS   --data, several roots separated by os.pathsep (":" on Linux)
    SCAN_DEPTH   --scan-depth
    PORT         --port
    ROOT_PATH    --root-path, the path the edge serves this under (/viewer)

The original Trame + vtk.js front end was mothballed on 2026-09-12 and lives on
the frozen ``trame`` branch.
"""

import argparse
import logging
import os
import time
import webbrowser

from .server.local import (
    LOOPBACK_HOSTS,
    LocalSession,
    bind_loopback,
    claim_instance,
    hand_over,
    instance_path,
    is_live,
    read_instance,
    release_instance,
)
from .server.sources import SERVER_SCAN_DEPTH, DirectorySource

log = logging.getLogger("cfdviewer")


def _env_int(name, default):
    raw = os.environ.get(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        raise SystemExit(f"cfd-viewer: {name}={raw!r} is not an integer")


def _env_roots():
    raw = os.environ.get("CASE_ROOTS", "").strip()
    return [r for r in raw.split(os.pathsep) if r] or None


def main(argv=None, default_mode="server"):
    """The console script; the frozen Windows launcher passes ``default_mode="local"``."""
    parser = argparse.ArgumentParser(prog="cfd-viewer", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--data",
        action="append",
        help="directory holding OpenFOAM cases, or a single case directory; "
             "repeat for several roots (server mode default: $CASE_ROOTS, else ./data)",
    )
    parser.add_argument(
        "folders", nargs="*", metavar="FOLDER",
        help="more roots, as --data; a folder dropped onto cfd-viewer.exe arrives here",
    )
    parser.add_argument(
        "--scan-depth",
        type=int,
        default=_env_int("SCAN_DEPTH", SERVER_SCAN_DEPTH),
        metavar="N",
        help="directory levels below each root to search for cases (default "
             f"{SERVER_SCAN_DEPTH}; cases are found at any level up to it, as "
             "cfd-backend finds them, and never inside another case)",
    )
    parser.add_argument("--port", type=int,
                        help="server mode default: $PORT, else 5003; local mode: a free port")
    # Not from $HOST: equa-deployment uses HOST for the public domain, and zsh
    # sets it to the machine name.
    parser.add_argument("--host", help="server mode default 0.0.0.0; local mode: 127.0.0.1 only")
    parser.add_argument(
        "--root-path",
        default=os.environ.get("ROOT_PATH", ""),
        metavar="PATH",
        help="serve under PATH (e.g. /viewer) as well as at the root, for an "
             "edge proxy that does not strip it (default: $ROOT_PATH, else none)",
    )
    parser.add_argument(
        "--mode",
        choices=["server", "local"],
        default=default_mode,
        help=f"run mode (default: {default_mode}). Server mode is what the "
             "cfd-backend container runs: an empty --data root is not fatal -- "
             "cases are picked up as they appear, so an empty CFD_HOME does not "
             "restart-loop the service. Local mode is one user's own machine: "
             "loopback only, opens the browser, folders added from the start screen",
    )
    parser.add_argument(
        "--no-browser", action="store_true",
        help="local mode: print the URL, token included, instead of opening a browser",
    )
    parser.add_argument(
        "--server",
        dest="mode",
        action="store_const",
        const="server",
        help="alias for --mode server, kept for the cfd-viz image's command line",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
    logging.getLogger("aiohttp.server").setLevel(logging.WARNING)

    if args.scan_depth < 0:
        parser.error("--scan-depth must be 0 or more")
    roots = (args.data or []) + args.folders
    if args.mode == "local":
        if (args.host or "127.0.0.1") not in LOOPBACK_HOSTS:
            parser.error("local mode listens on 127.0.0.1 only; "
                         "use --mode server to serve a network")
        source = DirectorySource([], depth=args.scan_depth)
        for root in roots:
            source.add_root(root)
        return _serve_local(source, roots, args)
    source = DirectorySource(roots or _env_roots() or ["data"], depth=args.scan_depth)
    cases = source.list()
    if not cases:
        msg = (
            f"no OpenFOAM case found under {source.describe()!r} "
            "(a case is a directory containing system/controlDict)"
        )
        # Server mode keeps running and discovers cases on demand as they
        # appear -- a solve writing its first time step must not need a viewer
        # restart.
        log.warning("%s; serving empty, will pick up cases on demand", msg)
    else:
        log.info("%d case(s) under %s: %s",
                 len(cases), source.describe(), ", ".join(c.name for c in cases))

    from .server.app import serve

    port = args.port if args.port is not None else _env_int("PORT", 5003)
    serve(source, host=args.host or "0.0.0.0", port=port, mode=args.mode,
          root_path=args.root_path)


def _serve_local(source, folders, args):
    """One viewer per user: join a running one, or start and record this one."""
    from .server.app import serve

    path = instance_path()
    for _ in range(3):
        found = read_instance(path)
        if found and _live(path, *found):
            port, token = found
            hand_over(port, token, folders)
            _show(f"http://127.0.0.1:{port}/?t={token}", args)
            return 0
        if found:
            path.unlink(missing_ok=True)  # stale: a crash, or another program took the port
        sock = bind_loopback(args.port or 0)
        session = LocalSession(sock.getsockname()[1])
        if claim_instance(path, session):
            break
        sock.close()  # another launch claimed it a moment ago; join that one
    else:
        raise SystemExit("cfd-viewer: could neither start nor find a running viewer")
    try:
        _show(session.url(), args)
        serve(source, host="127.0.0.1", port=session.port, mode="local",
              local=session, sock=sock)
    except KeyboardInterrupt:
        pass
    finally:
        release_instance(path, session)
    return 0


def _live(path, port, token):
    """Whether the recorded viewer answers; one that was just recorded may still
    be starting, so give a fresh file a few seconds."""
    try:
        fresh = time.time() - path.stat().st_mtime < 15
    except OSError:
        return False
    deadline = time.monotonic() + (10 if fresh else 0)
    while True:
        if is_live(port, token):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.2)


def _show(url, args):
    if args.no_browser:
        print(url, flush=True)
    else:
        webbrowser.open(url)

if __name__ == "__main__":
    main()
