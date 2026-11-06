"""Gemini CLI on Vertex AI, inside Harbor (software_engineering on Modal only).

Same design as the shared runner's `vertex` route (docs/gemini_vertex.md): a relay in
the sandbox pins the model and sends Google-native bodies to Vertex with a short-lived
service-account token read per request, and the host rewrites the token file every 45
minutes. Harbor needs its own copy for two reasons: gemini_cli_runner.py's relay is
part of the episode runner, which Harbor does not use, and agents here run up to 100
minutes, longer than one token lasts. As in the shared runner, an agent that reads the
token can use it for up to an hour.

The relay runs on Harbor's ACP runner venv, the one Python every task image has after
install. The CLI is launched in the ACP mode the existing configs use, so
agent/acp-events.jsonl is what the judge renders.
"""
import asyncio
import json
import os
import shlex
import tempfile

from harbor.agents.installed.acp import AcpAgent

from core.vertex_token import mint

RELAY_PORT = 8765
TOKEN_FILE = "/tmp/vertex_token"
RELAY_FILE = "/tmp/vertex_relay.py"
REFRESH_S = 45 * 60

# argv: model id, GCP project. Forwards streamed bytes unchanged.
RELAY = r'''
import json, sys, urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
MODEL, PROJECT = sys.argv[1:3]
def nest_tool_media(body):
    # Vertex rejects media beside a functionResponse; see gemini_cli_runner.nest_tool_media.
    for content in body.get("contents") or []:
        kept = []
        for part in content.get("parts") or []:
            if ("inlineData" in part or "fileData" in part) and kept and "functionResponse" in kept[-1]:
                kept[-1]["functionResponse"].setdefault("parts", []).append(part)
            else:
                kept.append(part)
        content["parts"] = kept
    return body
class Relay(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def do_POST(self):
        path, _, query = self.path.partition("?")
        method = path.rsplit(":", 1)[-1]
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        url = (f"https://aiplatform.googleapis.com/v1/projects/{PROJECT}/locations/global/publishers/google"
               f"/models/{urllib.parse.quote(MODEL, safe='')}:{method}" + (f"?{query}" if query else ""))
        token = open("/tmp/vertex_token").read().strip()
        request = urllib.request.Request(url, data=json.dumps(nest_tool_media(body)).encode(), method="POST", headers={
            "Authorization": f"Bearer {token}", "Content-Type": "application/json",
            "Accept": self.headers.get("Accept", "application/json")})
        try:
            response = urllib.request.urlopen(request, timeout=900)
        except urllib.error.HTTPError as error:
            response = error
        self.send_response(response.status)
        self.send_header("Content-Type", response.headers.get("Content-Type", "application/json"))
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        while (chunk := response.read1(65536)):
            self.wfile.write(chunk)
            self.wfile.flush()
ThreadingHTTPServer(("127.0.0.1", 8765), Relay).serve_forever()
'''


class VertexGeminiAcp(AcpAgent):
    """The ACP agent, plus the relay, the token refresher and the thinking setting."""

    async def _upload(self, environment, text, target):
        with tempfile.NamedTemporaryFile("w", suffix=".tmp") as local:
            local.write(text)
            local.flush()
            await environment.upload_file(local.name, target)

    async def _keep_token_fresh(self, environment, service_account):
        while True:
            await asyncio.sleep(REFRESH_S)
            await self._upload(environment, await asyncio.to_thread(mint, service_account), TOKEN_FILE)

    async def run(self, instruction, environment, context):
        service_account = os.environ["VERTEX_SERVICE_ACCOUNT"]
        project = service_account.split("@")[1].split(".")[0]
        model = self.model_name.split("/", 1)[1]
        await self._upload(environment, await asyncio.to_thread(mint, service_account), TOKEN_FILE)
        await self._upload(environment, RELAY, RELAY_FILE)
        # `--model cheatbench-high` in the registry entry selects this alias: the
        # entry's reasoning_effort, delivered as in the shared runner's route.
        settings = {"security": {"auth": {"selectedType": "gemini-api-key"}},
                    "general": {"enableAutoUpdate": False},
                    "modelConfigs": {"customAliases": {"cheatbench-high": {"modelConfig": {
                        "model": model,
                        "generateContentConfig": {"thinkingConfig": {
                            "includeThoughts": True, "thinkingLevel": "HIGH"}}}}}}}
        await self.exec_as_agent(environment, command=(
            f"mkdir -p ~/.gemini && printf %s {shlex.quote(json.dumps(settings))} > ~/.gemini/settings.json"))
        await self.exec_as_root(environment, command=(
            f"chmod 644 {TOKEN_FILE} {RELAY_FILE} && "
            f"setsid nohup {self._RUNNER_VENV_PATH}/bin/python {RELAY_FILE} {shlex.quote(model)} {shlex.quote(project)} "
            "> /tmp/vertex_relay.log 2>&1 < /dev/null &"))
        refresher = asyncio.create_task(self._keep_token_fresh(environment, service_account))
        try:
            await super().run(instruction, environment, context)
        finally:
            refresher.cancel()
