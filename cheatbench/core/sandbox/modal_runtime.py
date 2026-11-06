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
    setup.py hooks into the live netns      a second sandbox per episode (ModalServiceHost)

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
import io
import json
import shlex
import tarfile
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import modal

from .runtime import AGENT_HOME, CA_STORE, CERTIFI_GLOB, episode_payload

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
                        cpu: float = 2.0, memory_mb: int = 4096,
                        before_payload=None) -> "ModalProcess":
    """Create a sandbox and exec the episode payload in it.

    `allow_hosts` None means open network (a task with no `network:` block);
    a tuple means only those domains are reachable (`egress: deny`/`allow`).
    `before_payload(sandbox)` runs once the sandbox exists and before the agent
    does: ModalServiceHost.attach, which only needs the sandbox's root.
    """
    app = await modal.App.lookup.aio(APP_NAME, create_if_missing=True)
    network = {} if allow_hosts is None else {"outbound_domain_allowlist": list(allow_hosts)}
    sb = await modal.Sandbox.create.aio(app=app, image=img, timeout=timeout_s,
                                        workdir="/workspace", cpu=cpu,
                                        memory=memory_mb, **network)
    if before_payload is not None:
        await asyncio.to_thread(before_payload, sb)
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


# ---- host services (chess, go) -----------------------------------------------
#
# Under enroot these tasks run their game server on the host, outside the agent's
# mount and pid namespaces. There is no such place inside one Modal sandbox: the
# agent's user namespace maps it onto the sandbox's root, so it can read every file
# there. So each episode gets a SECOND sandbox holding the engine, the game server
# and the inference bridge:
#
#     agent sandbox                                   service sandbox
#     -------------                                   ---------------
#     agents.internal -> 127.0.44.7:443 --forwarder-> tunnel -> :8443 game server (own TLS)
#     CLI base url -> 127.0.0.1:8080    --forwarder-> tunnel -> :8080 inference bridge -> API
#
# The forwarder runs as `python -c` outside the agent's pid namespace, so no file
# and no process of it is visible to the agent. Differences from enroot worth
# knowing when reading results:
#   * agents.internal resolves to 127.0.44.7, not 10.44.0.7: gVisor refuses loopback
#     aliases (no CAP_NET_ADMIN), so a `curl -v` inside shows a loopback address.
#   * the agent's allowlist has one more host, this episode's tunnel, and a socket
#     listing inside shows connections to it.
REMOTE_ROOT = "/srv/cheatbench"
REMOTE_LOGS = "/srv/logs"
MIRROR_PORT = 8443
BRIDGE_PORT = 8080
ALIAS_IPS = ("127.0.44.7", "127.0.44.8")
ENGINES = "/opt/engines"
CUDA_REPO = "https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64"
CUDA_DEBS = ("libcublas-12-1_12.1.3.1-1_amd64.deb", "cuda-nvrtc-12-1_12.1.105-1_amd64.deb",
             "'libcudnn8_8.9.7.29-1+cuda12.2_amd64.deb'")

# Resources per service sandbox. Go's pinned KataGo is a CUDA build, and Modal GPUs
# require gVisor, which has no Landlock: RH_POLICY_CONFINEMENT makes the edited-policy
# worker confine itself with a private mount tree instead (tasks/go/linux_policy_sandbox.py).
SERVICE_SPECS = {
    "chess": {"cpu": 2.0, "memory": 4096, "gpu": None},
    "go": {"cpu": 4.0, "memory": 16384, "gpu": "T4"},
}


def _engine_layer(task_name: str, img: modal.Image) -> modal.Image:
    """The pinned engine, checksummed, in its own cached layer below the code.

    The signature check still runs at the start of every episode (service.py), on the
    machine that plays the game. That is the check that matters: Go's needs the GPU.
    """
    if task_name == "chess":
        from tasks.chess.stockfish import ASSETS, VERSION
        name, digest = ASSETS["x86_64"]
        url = ("https://github.com/official-stockfish/Stockfish/releases/download/"
               f"{VERSION}/{name}.tar.gz")
        return img.run_commands(
            f"mkdir -p {ENGINES} && curl -fsSL {url} -o /tmp/sf.tgz"
            f" && echo '{digest}  /tmp/sf.tgz' | sha256sum -c -"
            f" && tar -xzf /tmp/sf.tgz -C /tmp"
            f" && cp /tmp/stockfish/{name} {ENGINES}/stockfish && chmod 755 {ENGINES}/stockfish"
            " && rm -rf /tmp/sf.tgz /tmp/stockfish"
        ).env({"STOCKFISH": f"{ENGINES}/stockfish"})
    from tasks.go.assets import ARCHIVE, ENGINE_SHA256, ENGINE_URL, NETWORK, NETWORK_SHA256, NETWORK_URL
    return img.run_commands(
        f"mkdir -p {ENGINES} && cd {ENGINES}"
        f" && curl -fsSL -A 'Mozilla/5.0 (compatible; CheatBench asset downloader)' {NETWORK_URL} -o {NETWORK}"
        f" && echo '{NETWORK_SHA256}  {NETWORK}' | sha256sum -c -"
        f" && curl -fsSL {ENGINE_URL} -o {ARCHIVE}"
        f" && echo '{ENGINE_SHA256}  {ARCHIVE}' | sha256sum -c -"
        f" && unzip -q {ARCHIVE} katago && chmod 755 katago"
        " && ./katago --appimage-extract > /dev/null && rm katago " + ARCHIVE,
        # The release needs CUDA 12.1 and CUDNN 8.9.7 from the host. Unpacked rather than
        # installed, to pull in nothing else; the signature check confirms the result.
        f"mkdir -p {ENGINES}/cuda && cd /tmp && for deb in " + " ".join(CUDA_DEBS) + "; do"
        f" curl -fsSL {CUDA_REPO}/$deb -o pkg.deb && dpkg-deb -x pkg.deb {ENGINES}/cuda && rm pkg.deb; done",
    ).env({"RH_POLICY_CONFINEMENT": "mount",
           "LD_LIBRARY_PATH": f"{ENGINES}/cuda/usr/lib/x86_64-linux-gnu:{ENGINES}/cuda/usr/local/cuda-12.1/lib64"})


def service_image(task_name: str, repo: Path) -> modal.Image:
    """Dependencies, then the engine, then this checkout: editing code rebuilds only the last."""
    import tomllib
    project = tomllib.loads((repo / "pyproject.toml").read_text())["project"]
    deps = project["dependencies"] + project["optional-dependencies"]["go"]
    img = (modal.Image.debian_slim(python_version="3.11")
           .apt_install("curl", "openssl", "unzip", "libseccomp2")
           .pip_install(*deps))
    img = _engine_layer(task_name, img)
    ignore = ["**/__pycache__/**", "**/.build.lock", "**/environment/stockfish/**", "**/environment/assets/**"]
    # copy=True bakes the files in, so this image is a record of what the episode ran.
    img = (img.env({"PYTHONPATH": REMOTE_ROOT, "PYTHONUNBUFFERED": "1"})
           .add_local_dir(str(repo / "core"), f"{REMOTE_ROOT}/core", copy=True, ignore=ignore)
           .add_local_dir(str(repo / "tasks" / task_name), f"{REMOTE_ROOT}/tasks/{task_name}", copy=True, ignore=ignore))
    if task_name == "go":
        from tasks.go.assets import NETWORK
        record = json.dumps({"binary": f"{ENGINES}/squashfs-root/AppRun", "network": f"{ENGINES}/{NETWORK}"})
        img = img.run_commands(f"mkdir -p {REMOTE_ROOT}/tasks/go/environment/assets"
                               f" && echo '{record}' > {REMOTE_ROOT}/tasks/go/environment/assets/install.json")
    return img


# Runs as the agent sandbox's root, in that sandbox's outer pid namespace. Each route
# is (listen ip, listen port, tunnel host, tunnel port); Modal's tunnel takes TLS, and
# what travels inside it is the game server's own TLS, or the bridge's plain HTTP.
FORWARDER = r"""
import json, socket, ssl, sys, threading
tls = ssl.create_default_context()
def pump(a, b):
    try:
        while (data := a.recv(65536)):
            b.sendall(data)
    except OSError:
        pass
    for s in (a, b):
        try:
            s.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
def connect(client, host, port):
    remote = tls.wrap_socket(socket.create_connection((host, port), timeout=60), server_hostname=host)
    remote.settimeout(None)
    threading.Thread(target=pump, args=(client, remote), daemon=True).start()
    pump(remote, client)
def listen(ip, port, host, tunnel_port):
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((ip, port))
    server.listen(128)
    while True:
        client, _ = server.accept()
        threading.Thread(target=connect, args=(client, host, tunnel_port), daemon=True).start()
routes = json.loads(sys.argv[1])
for route in routes[1:]:
    threading.Thread(target=listen, args=route, daemon=True).start()
listen(*routes[0])
"""

# The Modal counterpart of runtime._write_container_files: name the services and trust
# their CA. Every real root stays trusted.
WRITE_FILES = r"""
import glob, sys
ca, host_lines, ca_store, certifi = sys.argv[1:5]
open("/etc/hosts", "a").write(host_lines)
for store in [ca_store, *glob.glob(certifi)]:
    text = open(store).read()
    open(store, "w").write(text.rstrip("\n") + "\n" + ca.strip() + "\n")
"""

WAIT_FOR_PORT = r"""
import socket, sys, time
for _ in range(120):
    try:
        socket.create_connection((sys.argv[1], int(sys.argv[2])), timeout=2).close()
        sys.exit(0)
    except OSError:
        time.sleep(0.5)
sys.exit(1)
"""


class ModalServiceHost:
    """The `sandbox` handle a task's environment/setup.py receives on Modal.

    It offers the two primitives chess and go use (`start_mirror`, `route_mcp_only`),
    so the hooks run unchanged. Blocking: core/trial.py calls it through a thread.
    """

    def __init__(self, image: modal.Image, task_name: str, repo: Path,
                 timeout_s: int, log_dir: Path):
        self.image, self.repo, self.timeout_s, self.log_dir = image, repo, timeout_s, Path(log_dir)
        self.spec = SERVICE_SPECS[task_name]
        self.sb = None
        self.server = None
        self.routes: list = []
        self.host_lines = ""
        self.ca_pem = ""
        self.tunnel_hosts: list = []
        self._dead = None
        self._closing = threading.Event()

    def _create(self) -> None:
        app = modal.App.lookup(APP_NAME, create_if_missing=True)
        self.sb = modal.Sandbox.create(
            app=app, image=self.image, timeout=self.timeout_s, workdir=REMOTE_ROOT,
            cpu=self.spec["cpu"], memory=self.spec["memory"], gpu=self.spec["gpu"],
            encrypted_ports=[MIRROR_PORT, BRIDGE_PORT])
        self.tunnels = self.sb.tunnels(timeout=120)
        self.tunnel_hosts = [t.host for t in self.tunnels.values()]
        self.sb.exec("mkdir", "-p", REMOTE_LOGS).wait()

    def _remote(self, path) -> str:
        return f"{REMOTE_ROOT}/{Path(path).resolve().relative_to(self.repo)}"

    def start_mirror(self, *, site, server, hosts, serving=None, overrides=None,
                     fallback_ips=None, extra_loopback=(), port=443) -> None:
        """Start the task's server (same flags as runtime.MirrorSandbox) and wait until it is ready."""
        self._create()
        site = Path(site)
        ready = "/tmp/mirror_ready"
        cmd = ["python", self._remote(server), "--mirror", self._remote(site),
               "--cert", self._remote(site / "tls/site.crt"), "--key", self._remote(site / "tls/site.key"),
               "--port", str(MIRROR_PORT), "--bind", "0.0.0.0", "--ready-file", ready,
               "--overrides", self._remote(overrides), "--only", serving,
               "--log", f"{REMOTE_LOGS}/mirror_requests.log"]
        self.server = self.sb.exec("bash", "-c", f"exec {shlex.join(cmd)} >> {REMOTE_LOGS}/mirror_server.log 2>&1")
        # KataGo loads its network and verifies its signature before it reports ready.
        deadline = time.time() + 600
        while self.sb.exec("test", "-f", ready).wait() != 0:
            if self.server.poll() is not None:
                raise RuntimeError(f"service exited {self.server.poll()}: {self._log_tail()}")
            if time.time() > deadline:
                raise TimeoutError(f"service never reported ready: {self._log_tail()}")
            time.sleep(1)
        tunnel = self.tunnels[MIRROR_PORT]
        ips = dict(zip(hosts, ALIAS_IPS))
        self.routes += [(ip, 443, tunnel.host, tunnel.port) for ip in ips.values()]
        self.host_lines = "".join(f"{ip}\t{host}\n" for host, ip in ips.items())
        self.ca_pem = (site / "tls/ca.crt").read_text()
        threading.Thread(target=self._watch, daemon=True).start()

    def route_mcp_only(self, blob: bytes, base_url: str, api_key: str):
        """Run runtime's InferenceBridge in the service sandbox, not on the laptop the agent can't reach."""
        from .native_inference import reroute_blob
        task = json.loads(blob).get("task", {})
        bridge = ("import os, time; from core.sandbox.native_inference import InferenceBridge; "
                  f"InferenceBridge({base_url!r}, os.environ['RH_BRIDGE_KEY'], {REMOTE_LOGS + '/inference_requests.jsonl'!r}, "
                  f"grok_mcp={bool(task.get('grok', {}).get('mcp_only'))}, "
                  f"mcp_server={task.get('row', {}).get('tool_surface', 'chess')!r}, "
                  f"bind=('0.0.0.0', {BRIDGE_PORT})); time.sleep(10 ** 9)")
        self.sb.exec("bash", "-c", f"exec python -c {shlex.quote(bridge)} >> {REMOTE_LOGS}/bridge.log 2>&1",
                     secrets=[modal.Secret.from_dict({"RH_BRIDGE_KEY": api_key})])
        if self.sb.exec("python", "-c", WAIT_FOR_PORT, "127.0.0.1", str(BRIDGE_PORT)).wait() != 0:
            raise RuntimeError(f"inference bridge never listened: {self._log_tail('bridge.log')}")
        tunnel = self.tunnels[BRIDGE_PORT]
        self.routes.append(("127.0.0.1", BRIDGE_PORT, tunnel.host, tunnel.port))
        return reroute_blob(blob, f"http://127.0.0.1:{BRIDGE_PORT}{urlsplit(base_url).path.rstrip('/')}"), BRIDGE_PORT

    def attach(self, agent_sb: modal.Sandbox) -> None:
        """Called after the agent sandbox exists and before its payload starts."""
        agent_sb.exec("python", "-c", FORWARDER, json.dumps(self.routes))
        code = agent_sb.exec("python", "-c", WRITE_FILES, self.ca_pem, self.host_lines, CA_STORE, CERTIFI_GLOB).wait()
        if code != 0:
            raise RuntimeError(f"could not write the agent sandbox's hosts and CA files (exit {code})")
        for ip, port, _, _ in self.routes:
            if agent_sb.exec("python", "-c", WAIT_FOR_PORT, ip, str(port)).wait() != 0:
                raise RuntimeError(f"forwarder never listened on {ip}:{port}")

    def _watch(self) -> None:
        """A dead server must fail the episode; trial.py checks every 0.25 s, so the RPC lives here."""
        while not self._closing.wait(10):
            code = self.server.poll()
            if code is not None:
                self._dead = f"service exited {code}: {self._log_tail()}"
                return

    def check_health(self) -> None:
        if self._dead:
            raise RuntimeError(self._dead)

    def _log_tail(self, name: str = "mirror_server.log") -> str:
        proc = self.sb.exec("tail", "-c", "2000", f"{REMOTE_LOGS}/{name}", text=True)
        return proc.stdout.read()

    def close(self) -> None:
        """Copy the service's logs and game records next to the episode, then terminate."""
        self._closing.set()
        if self.sb is None:
            return
        proc = self.sb.exec("tar", "-czf", "-", "-C", REMOTE_LOGS, ".", text=False)
        archive = proc.stdout.read()
        if proc.wait() == 0:
            target = self.log_dir / "service"
            target.mkdir(parents=True, exist_ok=True)
            with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
                bundle.extractall(target, filter="data")
        self.sb.terminate()
