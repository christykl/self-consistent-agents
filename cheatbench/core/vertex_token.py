"""Short-lived Vertex AI access tokens for a service account, minted from ADC.

Two HTTP calls, stdlib only:

  1. ADC (`gcloud auth application-default login`, an `authorized_user` file)
     -> a 1-hour access token for the person running the eval.
  2. That token -> IAM Credentials `generateAccessToken` for the service
     account, which needs `roles/iam.serviceAccountTokenCreator` on it.

The episode only ever sees token (2), so an agent that reads it can do what the
service account can (here: roles/aiplatform.user on one project) for at most an
hour. See docs/gemini_vertex.md.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

ADC_FILE = Path(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
                or Path.home() / ".config/gcloud/application_default_credentials.json")
SCOPE = "https://www.googleapis.com/auth/cloud-platform"


def _post(url: str, body: bytes, headers: dict) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=headers)) as r:
        return json.load(r)


def adc_token() -> str:
    adc = json.loads(ADC_FILE.read_text())
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token", "client_id": adc["client_id"],
        "client_secret": adc["client_secret"], "refresh_token": adc["refresh_token"],
    }).encode()
    return _post("https://oauth2.googleapis.com/token", body, {})["access_token"]


def mint(service_account: str) -> str:
    """A fresh 1-hour cloud-platform token for `service_account`."""
    url = ("https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/"
           f"{service_account}:generateAccessToken")
    body = json.dumps({"scope": [SCOPE], "lifetime": "3600s"}).encode()
    return _post(url, body, {"Authorization": f"Bearer {adc_token()}",
                             "Content-Type": "application/json"})["accessToken"]
