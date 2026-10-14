"""
QuantConnect cloud client: compile and backtest generated code.

Auth follows QuantConnect's API docs (SHA-256 of "token:timestamp",
sent as HTTP Basic with the user id):
https://www.quantconnect.com/docs/v2/cloud-platform/api-reference/authentication

STATUS: written from the docs but NOT yet run against the live API.
The endpoint paths below come from the docs' API reference index; the
exact request/response field names still need checking once Jared's
keys arrive. Run `python -m qc_eval.qc_client` to test authentication.

Set QC_USER_ID and QC_API_TOKEN (and optionally QC_ORG_ID) in the env.
"""

import os
import time
from base64 import b64encode
from hashlib import sha256

import requests

BASE_URL = "https://www.quantconnect.com/api/v2"


class QCClient:
    def __init__(self, user_id: str | None = None, api_token: str | None = None,
                 org_id: str | None = None):
        self.user_id = user_id or os.environ["QC_USER_ID"]
        self.api_token = api_token or os.environ["QC_API_TOKEN"]
        self.org_id = org_id or os.environ.get("QC_ORG_ID")

    # ---- low level -------------------------------------------------------
    def _headers(self) -> dict:
        timestamp = str(int(time.time()))
        hashed = sha256(f"{self.api_token}:{timestamp}".encode()).hexdigest()
        auth = b64encode(f"{self.user_id}:{hashed}".encode()).decode()
        return {"Authorization": f"Basic {auth}", "Timestamp": timestamp}

    def _post(self, path: str, payload: dict | None = None) -> dict:
        resp = requests.post(f"{BASE_URL}/{path}", headers=self._headers(),
                             json=payload or {}, timeout=60)
        resp.raise_for_status()
        return resp.json()

    def authenticate(self) -> bool:
        return bool(self._post("authenticate").get("success"))

    # ---- project / compile / backtest -------------------------------------
    # TODO(verify field names against live API responses)
    def create_project(self, name: str) -> int:
        payload = {"name": name, "language": "Py"}
        if self.org_id:
            payload["organizationId"] = self.org_id
        data = self._post("projects/create", payload)
        return data["projects"][0]["projectId"]

    def update_main(self, project_id: int, code: str) -> None:
        self._post("files/update", {"projectId": project_id,
                                    "name": "main.py", "content": code})

    def compile(self, project_id: int, poll_seconds: float = 2.0,
                max_wait: float = 120) -> tuple[bool, str, list]:
        data = self._post("compile/create", {"projectId": project_id})
        compile_id = data["compileId"]
        waited = 0.0
        while waited < max_wait:
            res = self._post("compile/read", {"projectId": project_id,
                                              "compileId": compile_id})
            state = res.get("state")
            if state == "BuildSuccess":
                return True, compile_id, res.get("logs", [])
            if state == "BuildError":
                return False, compile_id, res.get("logs", [])
            time.sleep(poll_seconds)
            waited += poll_seconds
        return False, compile_id, ["compile timed out"]

    def backtest(self, project_id: int, compile_id: str, name: str,
                 poll_seconds: float = 5.0, max_wait: float = 900) -> dict:
        data = self._post("backtests/create", {"projectId": project_id,
                                               "compileId": compile_id,
                                               "backtestName": name})
        backtest_id = data["backtest"]["backtestId"]
        waited = 0.0
        while waited < max_wait:
            res = self._post("backtests/read", {"projectId": project_id,
                                                "backtestId": backtest_id})
            bt = res.get("backtest", {})
            if bt.get("error") or bt.get("stacktrace"):
                return {"status": "runtime_error", "error": bt.get("error"),
                        "stacktrace": bt.get("stacktrace"), "raw": bt}
            if bt.get("completed"):
                return {"status": "completed",
                        "statistics": bt.get("statistics", {}),
                        "total_orders": bt.get("statistics", {}).get("Total Orders"),
                        "raw": bt}
            time.sleep(poll_seconds)
            waited += poll_seconds
        return {"status": "timeout"}


if __name__ == "__main__":
    print("authenticated:", QCClient().authenticate())
