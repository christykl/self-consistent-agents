"""The Modal backend: one episode in one Modal Sandbox.

The enroot backend (runtime.py) runs one command per episode -- the runner's
bootstrap on argv, the blob on stdin, turn records on stderr, one JSON line on
stdout -- and this backend keeps that contract exactly. Only the container
around it changes:

    enroot (runtime.py)                     Modal (this file)
    -------------------                     -----------------
    squashfs built from ./Dockerfile        modal.Image.from_dockerfile(Dockerfile)
    `unshare --user --pid` + enroot start   modal.Sandbox.create (gVisor)
    payload = episode_payload(bootstrap)    the SAME payload, via sb.exec("bash", "-c", ...)
    key passed by NAME via enroot -e        key passed as a modal.Secret (never argv)
    egress.py firewall (`network:` block)   outbound_domain_allowlist
    setup.py hooks into the live netns      not supported (refused in run.py)

The privilege drop in `episode_payload` (a nested user namespace in which
container-root is uid 1000) works unchanged under gVisor: verified that the
agent sees `uid=1000(user)` and can still write anywhere in its own filesystem,
as it can under enroot.

Two differences worth knowing when reading results:

  * Modal's domain allowlist does not check TLS SNI / Host headers the way
    egress_relay.py does, so a CDN-fronted allowlisted address could serve
    another site. Weaker than the enroot firewall for `egress: deny` tasks.
  * The adapter's runtime (Node + the CLI) is pre-baked into the image as a
    cache layer (`image(..., prebake=...)`), so the in-episode `check || install`
    finds it and skips the install. The enroot image deliberately does not do
    this; see the Dockerfile header. It is a performance choice only.
"""
from __future__ import annotations

import asyncio
import base64
from pathlib import Path

import modal

from .runtime import AGENT_HOME, episode_payload

APP_NAME = "cheatbench"


def image(dockerfile: Path, prebake: str = "") -> modal.Image:
    """The task image as a Modal image, optionally with the agent CLI baked in.

    `prebake` is the adapter's own install script (Agent.install()["install"]),
    run at build time with HOME set to the agent's home, so the files land
    exactly where the in-episode install would have put them.
    """
    img = modal.Image.from_dockerfile(str(dockerfile))
    if prebake:
        # Each run_commands entry becomes one Dockerfile RUN line, so the
        # multi-line script travels base64-encoded.
        b64 = base64.b64encode(prebake.encode()).decode()
        img = img.run_commands(
            f"mkdir -p {AGENT_HOME} && echo {b64} | base64 -d > /tmp/prebake.sh"
            f" && HOME={AGENT_HOME} bash /tmp/prebake.sh && rm /tmp/prebake.sh")
    return img


async def build_image(img: modal.Image) -> modal.Image:
    """Build once up front, so concurrent episodes do not race to build it."""
    app = await modal.App.lookup.aio(APP_NAME, create_if_missing=True)
    return await img.build.aio(app)


async def start_episode(img: modal.Image, bootstrap: str, *, secrets: dict,
                        timeout_s: int, allow_hosts: tuple | None = None,
                        cpu: float = 2.0, memory_mb: int = 4096) -> "ModalProcess":
    """Create a sandbox and exec the episode payload in it.

    `allow_hosts` None means open network (a task with no `network:` block);
    a tuple means only those domains are reachable (`egress: deny`/`allow`).
    """
    app = await modal.App.lookup.aio(APP_NAME, create_if_missing=True)
    network = {} if allow_hosts is None else {"outbound_domain_allowlist": list(allow_hosts)}
    sb = await modal.Sandbox.create.aio(app=app, image=img, timeout=timeout_s,
                                        workdir="/workspace", cpu=cpu,
                                        memory=memory_mb, **network)
    proc = await sb.exec.aio("bash", "-c", episode_payload(bootstrap),
                             env={"PYTHONUNBUFFERED": "1"},
                             secrets=[modal.Secret.from_dict(secrets)],
                             text=False)
    return ModalProcess(sb, proc)


class ModalProcess:
    """A Modal ContainerProcess, wearing the parts of `asyncio.subprocess.Process`
    that core/trial.py uses, so its episode I/O loop is the same for both
    backends."""

    def __init__(self, sb: modal.Sandbox, proc):
        self.sandbox = sb
        self.pid = None
        self.returncode = None
        self.stdin = _Stdin(proc.stdin)
        self.stdout = _Reader(proc.stdout)
        self.stderr = _Reader(proc.stderr)
        self._proc = proc
        self._refresher = None
        # asyncio sets `returncode` as soon as the process exits, and trial.py
        # polls it (`while proc.returncode is None`), so watch for exit here too.
        self._exited = asyncio.ensure_future(self._watch_exit())

    async def _watch_exit(self) -> None:
        self.returncode = await self._proc.wait.aio()

    async def wait(self) -> int:
        if self.returncode is None:
            await asyncio.shield(self._exited)
        return self.returncode

    def kill(self) -> None:
        # Sync in asyncio's API; the sandbox itself is terminated in close().
        if self.returncode is None:
            self._exited.cancel()
            self.returncode = -9

    async def communicate(self):
        await self.wait()
        return b"", b""

    async def keep_file_fresh(self, path: str, make_text, every_s: float = 45 * 60) -> None:
        """Write `make_text()` to `path` in the sandbox now, then every `every_s`
        until close(). Used for 1-hour Vertex tokens (core/vertex_token.py)."""
        await self.sandbox.filesystem.write_text.aio(make_text(), path)

        async def loop():
            while True:
                await asyncio.sleep(every_s)
                text = await asyncio.to_thread(make_text)
                await self.sandbox.filesystem.write_text.aio(text, path)
        self._refresher = asyncio.ensure_future(loop())

    async def close(self) -> None:
        """Terminate the sandbox. Always called: an idle sandbox bills until its timeout."""
        self._exited.cancel()
        if self._refresher is not None:
            self._refresher.cancel()
        await self.sandbox.terminate.aio()


class _Stdin:
    """trial.py writes the whole blob once and then drains, so draining is
    also where EOF is sent. Modal's writer refuses a single write past its
    buffer limit (a 14 MB knowledge_work row hit it), so the blob is held
    here and sent in chunks, draining after each."""

    CHUNK = 4 << 20

    def __init__(self, writer):
        self._w = writer
        self._buf = b""

    def write(self, data: bytes) -> None:
        self._buf += data

    async def drain(self) -> None:
        for i in range(0, len(self._buf), self.CHUNK):
            self._w.write(self._buf[i:i + self.CHUNK])
            await self._w.drain.aio()
        self._w.write_eof()
        await self._w.drain.aio()

    def close(self) -> None:
        pass

    def is_closing(self) -> bool:
        return True


class _Reader:
    """`read()` and `readline()` over Modal's chunked byte stream."""

    def __init__(self, stream):
        self._chunks = stream.__aiter__()
        self._buf = b""

    async def _more(self) -> bool:
        try:
            self._buf += await self._chunks.__anext__()
            return True
        except StopAsyncIteration:
            return False

    async def readline(self) -> bytes:
        while b"\n" not in self._buf:
            if not await self._more():
                line, self._buf = self._buf, b""
                return line
        line, _, self._buf = self._buf.partition(b"\n")
        return line + b"\n"

    async def read(self) -> bytes:
        while await self._more():
            pass
        out, self._buf = self._buf, b""
        return out
