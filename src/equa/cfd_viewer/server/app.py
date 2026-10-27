"""HTTP layer: the scene endpoints plus the built client.

Deliberately thin. Everything CFD is in :mod:`server.scene`; everything visual
is in the browser. What this module adds is the concurrency discipline the spike
did not have:

* extraction runs in a **worker thread** (``asyncio.to_thread``), so a 3-second
  ``vtkStreamTracer`` no longer freezes the event loop and the server keeps
  answering ``/api/meta`` and static requests while it works;
* a single **lock** serialises access to the filter graph, which is shared
  mutable state -- two concurrent extractions on one ``FoamPipeline`` would
  interleave ``update_plane`` calls and hand each other the wrong geometry.

That is one case per process, still, as in the Trame app: fine behind the
per-user cfd-stack deployment, and the thing to revisit if the viewer is ever
shared by several users at once.
"""

import asyncio
import logging
import os
from pathlib import Path

from aiohttp import web

from .. import __version__
from ..foamviz import colors
from .local import INSTANCE_PATH, browse
from .scene import SceneSource
from .sources import AmbiguousCase, CaseNotFound

log = logging.getLogger("cfdviewer")

STOP = web.AppKey("stop", asyncio.Event)

PACKAGE = Path(__file__).resolve().parent.parent
# src/equa/cfd_viewer -> the checkout root, when running from a source tree.
CHECKOUT = PACKAGE.parent.parent.parent


def client_dir():
    """Where the built client is, first match wins:

    1. ``WEB_DIST_DIR``, as the equa service images set it;
    2. the client packaged into the wheel (``equa/cfd_viewer/web``);
    3. ``web/dist`` in a source checkout -- what cfd-backend's cfd-viz image
       serves, since it builds the client in place in a clone of this repo.

    None of them may exist in development, where `npm run dev` serves the
    client on its own port and proxies /api here (see web/vite.config.js); the
    index route then shows a hint page instead.
    """
    candidates = [PACKAGE / "web", CHECKOUT / "web" / "dist"]
    if os.environ.get("WEB_DIST_DIR"):
        candidates.insert(0, Path(os.environ["WEB_DIST_DIR"]))
    for path in candidates:
        if (path / "index.html").is_file():
            return path
    return candidates[-1]


DIST = client_dir()

_DEV_HINT = """<!doctype html><meta charset="utf-8">
<title>cfd-viewer</title>
<body style="font:14px system-ui;padding:2rem;max-width:34rem">
<h3>No client build</h3>
<p><code>web/dist</code> does not exist, so there is nothing to serve here.</p>
<p>For development run the Vite dev server, which proxies <code>/api</code> to
this process:</p>
<pre>cd web &amp;&amp; npm install &amp;&amp; npm run dev</pre>
<p>To serve the client from this process instead, build it once:</p>
<pre>cd web &amp;&amp; npm run build</pre>
</body>"""


# What the server can do, per run mode: ``server`` is the cockpit's cfd-viz and
# the platform's image, ``local`` a user's own machine (openspec
# local-desktop-viewer); ``hosted`` will add "Upload case" through the same flags.
MODES = {
    "server": {"canAddFolders": False, "canUpload": False},
    "local": {"canAddFolders": True, "canUpload": False},
}


def normalise_root_path(root_path):
    """``/viewer`` from ``/viewer/`` or ``viewer/``; ``""`` for the root."""
    root_path = (root_path or "").strip().strip("/")
    return f"/{root_path}" if root_path else ""


def make_app(source, mode="server", root_path="", local=None):
    """The aiohttp app over a case source (``sources.DirectorySource``).

    *root_path* (``/viewer``) is the path an edge proxy serves this under
    without stripping it, as equa-deployment's Traefik does (``ROOT_PATH``).
    Every route then answers both under it and at the root, as Starlette's
    ``root_path`` does for the other platform services: the edge sends
    ``/viewer/health``, the image's own HEALTHCHECK asks ``/health``. The
    cockpit's nginx strips ``/viz/`` itself and needs no root path.

    *local* (``local.LocalSession``) is required in ``local`` mode: its guard
    admits only the launching user's browser.
    """
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    if (mode == "local") != (local is not None):
        raise ValueError("local mode needs a LocalSession, and only local mode takes one")
    root_path = normalise_root_path(root_path)
    scene_source = SceneSource(source)
    # The filter graph is shared mutable state; one extraction at a time.
    lock = asyncio.Lock()

    async def in_thread(fn, *args):
        """Run a blocking VTK call off the event loop, one at a time."""
        async with lock:
            return await asyncio.to_thread(fn, *args)

    async def open_case(request):
        """Open the case ?case= denotes: an id, or a name exactly one case has.

        Anything else is a 404 with the reason. There is deliberately no
        fallback to the first case any more: showing a different case than the
        one asked for is worse than saying so (openspec standalone-viewer).
        """
        key = request.query.get("case") or ""
        if not key:
            raise web.HTTPNotFound(text="no case given: pass ?case=<id or name>")
        try:
            await in_thread(scene_source.open, key)
        except AmbiguousCase as exc:
            raise web.HTTPNotFound(
                text=f"case name {key!r} is ambiguous; use one of the ids "
                     f"{', '.join(exc.args[1])}")
        except CaseNotFound:
            raise web.HTTPNotFound(text=f"no case {key!r}")

    async def health(_request):
        """Up and accepting requests. Touches no case root, opens no case."""
        return web.Response(text="ok")

    async def config(_request):
        """What this server is and can do; the client's start screen reads it.
        Cheap by design: no case root is scanned and no case is opened."""
        answer = {"mode": mode, "version": __version__, **MODES[mode]}
        if local:
            answer["recentFolders"] = await asyncio.to_thread(local.recent.list)
        return web.json_response(answer)

    async def cases(_request):
        """``cases`` (names) as it always was, plus ``entries`` with the rest."""
        refs = await asyncio.to_thread(source.list)
        return web.json_response({"cases": [r.name for r in refs],
                                  "entries": [r.to_json() for r in refs]})

    async def meta(request):
        await open_case(request)
        return web.json_response(await in_thread(scene_source.meta))

    async def times(request):
        """Re-scan the case for time steps written since it was opened."""
        await open_case(request)
        return web.json_response({"times": await in_thread(scene_source.refresh_times)})

    async def field_range(request):
        """The data range for one field/component. Cheap by design -- see
        SceneSource.field_range for why this is not part of /api/scene."""
        await open_case(request)
        try:
            values = await in_thread(
                scene_source.field_range,
                request.query.get("field"),
                request.query.get("component"),
                request.query.get("robust") not in (None, "", "0", "false"),
            )
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc))
        return web.json_response({"range": values})

    async def scene(request):
        await open_case(request)
        try:
            blob = await in_thread(scene_source.scene, request.query)
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc))
        response = web.Response(body=blob, content_type="application/octet-stream")
        # Worth having on by default: the payload is float32 positions, repeated
        # normals and locally-coherent indices, which gzip takes to ~24% of raw
        # (16.2 -> 3.9 MB on s2; see tests/bench.py). Without this the wire size
        # looks far worse than the format deserves.
        response.enable_compression()
        return response

    async def lut(request):
        """The 256-entry colour table as 768 raw bytes.

        Sampled from the same matplotlib data the VTK transfer function uses, so
        the shader and a server-side VTK render agree on colour exactly rather
        than approximately. Cached hard on the client: a preset switch is a
        texture upload, never a geometry request.
        """
        name = request.query.get("name", "coolwarm")
        if name not in colors.PRESET_NAMES:
            raise web.HTTPBadRequest(text=f"no preset {name!r}")
        return web.Response(
            body=colors.rgb_table(name),
            content_type="application/octet-stream",
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )

    async def index(_request):
        page = DIST / "index.html"
        if not page.is_file():
            return web.Response(text=_DEV_HINT, content_type="text/html")
        # No-store on the shell only: it names hashed asset files, so a cached
        # copy after a redeploy points at assets that no longer exist.
        return web.FileResponse(page, headers={"Cache-Control": "no-store"})

    async def to_slash(request):
        # The client's URLs are relative (base ''), so the page only works at
        # /viewer/ -- at /viewer its assets would resolve against the parent.
        # with_path drops the query, and ?case= must survive the redirect.
        raise web.HTTPPermanentRedirect(
            request.rel_url.with_path(root_path + "/").with_query(request.query))

    async def folders(request):
        """Local mode's folder browser: drives, then subdirectories (D2)."""
        try:
            listing = await asyncio.to_thread(browse, request.query.get("path", ""))
        except OSError as exc:
            raise web.HTTPNotFound(text=f"cannot list {request.query.get('path')!r}: {exc}")
        return web.json_response(listing)

    async def add_folder(request):
        """Add a folder as a root, and to the recent folders."""
        try:
            folder = Path((await request.json())["path"]).resolve()
        except (ValueError, KeyError, TypeError):
            raise web.HTTPBadRequest(text='expected {"path": "<folder>"}')
        if not folder.is_dir():
            raise web.HTTPNotFound(text=f"no folder {str(folder)!r}")
        added = source.add_root(folder)
        await asyncio.to_thread(local.recent.add, folder)
        return web.json_response({"added": added, "path": str(folder)})

    async def instance(request):
        """Proof that this is the viewer the instance file names (D1)."""
        nonce = request.query.get("nonce", "")
        if not 16 <= len(nonce) <= 128:
            raise web.HTTPBadRequest(text="nonce: 16 to 128 characters")
        return web.json_response({"proof": local.proof(nonce)})

    async def quit_(_request):
        """Stop the server once this answer is out (D3)."""
        asyncio.get_running_loop().call_later(0.2, app[STOP].set)
        return web.json_response({"stopping": True})

    app = web.Application(middlewares=[local.guard] if local else [])
    app[STOP] = asyncio.Event()
    routes = {"/": index, "/health": health, "/api/config": config, "/api/cases": cases,
              "/api/meta": meta, "/api/times": times, "/api/range": field_range,
              "/api/scene": scene, "/api/lut": lut}
    if local:
        routes["/api/folders"] = folders
        routes[INSTANCE_PATH] = instance
    for prefix in dict.fromkeys(["", root_path]):
        for path, handler in routes.items():
            app.router.add_get(prefix + path, handler)
        if (DIST / "assets").is_dir():
            # Vite fingerprints these, so they can be cached forever.
            app.router.add_static(prefix + "/assets/", DIST / "assets")
    if local:
        app.router.add_post("/api/folders", add_folder)
        app.router.add_post("/api/quit", quit_)
    if root_path:
        app.router.add_get(root_path, to_slash)
    app["source"] = scene_source
    return app


def serve(source, host="0.0.0.0", port=5003, mode="server", root_path="",
          local=None, sock=None):
    root_path = normalise_root_path(root_path)
    log.info("cfd-viewer %s (%s mode) serving %s on http://%s:%d%s/",
             __version__, mode, source.describe(), host, port, root_path)
    app = make_app(source, mode=mode, root_path=root_path, local=local)
    if sock is not None:  # local mode binds first, to know its port
        asyncio.run(_serve_until_stopped(app, sock))
    else:
        web.run_app(app, host=host, port=port, print=None)


async def _serve_until_stopped(app, sock):
    """Local mode's server loop: until ``/api/quit``, or Ctrl+C."""
    runner = web.AppRunner(app)
    await runner.setup()
    try:
        await web.SockSite(runner, sock).start()
        await app[STOP].wait()
    finally:
        await runner.cleanup()
