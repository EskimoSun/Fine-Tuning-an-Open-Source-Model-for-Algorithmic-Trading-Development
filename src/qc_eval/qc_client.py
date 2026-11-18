"""QuantConnect Cloud API client for generated-code evaluation.

Set QC_USER_ID and QC_API_TOKEN (QC_ORG_ID optional). Live API integration
still needs verification with your account; tests use recorded-shape responses.
"""

from __future__ import annotations

import os
import time
from base64 import b64encode
from hashlib import sha256

import requests
from .config import load_env

BASE_URL = "https://www.quantconnect.com/api/v2"


class QCAPIError(RuntimeError):
    def __init__(self, endpoint, response):
        super().__init__(f"API request failed: {endpoint}")
        self.endpoint = endpoint
        self.response = response


class QCClient:
    def __init__(self, user_id: str | None = None, api_token: str | None = None,
                 org_id: str | None = None):
        load_env()
        self.user_id = user_id or os.environ["QC_USER_ID"]
        self.api_token = api_token or os.environ["QC_API_TOKEN"]
        self.org_id = org_id or os.environ.get("QC_ORG_ID")

    def _headers(self) -> dict:
        timestamp = str(int(time.time()))
        hashed = sha256(f"{self.api_token}:{timestamp}".encode()).hexdigest()
        auth = b64encode(f"{self.user_id}:{hashed}".encode()).decode()
        return {"Authorization": f"Basic {auth}", "Timestamp": timestamp}

    def _post(self, path: str, payload: dict | None = None) -> dict:
        resp = requests.post(f"{BASE_URL}/{path}", headers=self._headers(),
                             json=payload or {}, timeout=60)
        resp.raise_for_status()
        body = resp.json()
        if not body.get("success"):
            raise QCAPIError(path, body)
        return body

    def authenticate(self) -> bool:
        return bool(self._post("authenticate").get("success"))

    def create_project(self, name: str) -> int:
        payload = {"name": name, "language": "Py"}
        if self.org_id:
            payload["organizationId"] = self.org_id
        return self._post("projects/create", payload)["projects"][0]["projectId"]

    def update_main(self, project_id: int, code: str) -> None:
        self._post("files/update", {"projectId": project_id,
                                    "name": "main.py", "content": code})

    def _poll(self, endpoint, payload, finished, key, on_progress,
              poll_seconds, max_wait):
        deadline = time.monotonic() + max_wait
        while time.monotonic() < deadline:
            body = self._post(endpoint, payload)
            on_progress({key: body})
            if finished(body):
                return body
            time.sleep(min(poll_seconds, max(0, deadline - time.monotonic())))
        raise TimeoutError(f"Timed out polling {endpoint}; cloud job may still be running")

    def compile(self, project_id: int, poll_seconds: float = 2.0,
                max_wait: float = 120, on_progress=None) -> tuple[bool, str, list]:
        on_progress = on_progress or (lambda update: None)
        created = self._post("compile/create", {"projectId": project_id})
        compile_id = created["compileId"]
        on_progress({"compile_id": compile_id, "compile_created": created})
        res = self._poll(
            "compile/read", {"projectId": project_id, "compileId": compile_id},
            lambda body: body.get("state") in ("BuildSuccess", "BuildError"),
            "compilation", on_progress, poll_seconds, max_wait)
        return res["state"] == "BuildSuccess", compile_id, res.get("logs", [])

    @staticmethod
    def _runtime_failed(bt):
        return bool(bt.get("error") or bt.get("stacktrace")
                    or bt.get("hasInitializeError") or bt.get("status") == "Runtime Error")

    def backtest(self, project_id: int, compile_id: str, name: str,
                 poll_seconds: float = 5.0, max_wait: float = 900,
                 on_progress=None) -> dict:
        on_progress = on_progress or (lambda update: None)
        created = self._post("backtests/create", {"projectId": project_id,
                                                 "compileId": compile_id,
                                                 "backtestName": name})
        backtest_id = created["backtest"]["backtestId"]
        on_progress({"backtest_id": backtest_id, "backtest_created": created})
        res = self._poll(
            "backtests/read", {"projectId": project_id, "backtestId": backtest_id},
            lambda body: self._runtime_failed(body["backtest"]) or body["backtest"].get("completed"),
            "raw_backtest", on_progress, poll_seconds, max_wait)
        bt = res["backtest"]
        return {"status": "runtime_error" if self._runtime_failed(bt) else "completed",
                "backtest_id": backtest_id, "error": bt.get("error"),
                "stacktrace": bt.get("stacktrace"),
                "has_initialize_error": bt.get("hasInitializeError", False),
                "statistics": bt.get("statistics", {}),
                "trade_statistics": bt.get("totalPerformance", {}).get("tradeStatistics", {}),
                "runtime_statistics": bt.get("runtimeStatistics", {}),
                "total_orders": bt.get("statistics", {}).get("Total Orders"), "raw": bt}

    def read_logs(self, project_id, backtest_id, on_progress=None):
        on_progress = on_progress or (lambda update: None)
        logs = []
        on_progress({"logs": logs})
        while True:
            start = len(logs)
            page = self._post("backtests/read/log", {
                "projectId": project_id, "backtestId": backtest_id,
                "start": start, "end": start + 200, "query": ""})
            lines = page.get("logs", [])
            logs.extend(lines)
            on_progress({"logs": list(logs)})
            if not lines or len(logs) >= page.get("length", len(logs)):
                return logs

    def _read_ready(self, endpoint, payload, max_wait=120):
        """Orders and charts may initially return a successful 'loading' response."""
        return self._poll(endpoint, payload,
                          lambda body: body.get("status") != "loading",
                          "response", lambda update: None, 2, max_wait)

    def read_orders(self, project_id, backtest_id):
        """Fetch every page; never silently treat a truncated page as all orders."""
        orders, seen = [], set()
        while True:
            start = len(orders)
            page = self._read_ready("backtests/orders/read", {
                "projectId": project_id, "backtestId": backtest_id,
                "start": start, "end": start + 100})
            rows = page["orders"]
            if isinstance(rows, dict):
                rows = list(rows.values())
            if not rows:
                if len(orders) < page.get("length", len(orders)):
                    raise ValueError("Orders ended before the reported total")
                return orders
            for row in rows:
                order = row.get("order", row)
                key = order["id"]
                if key in seen:
                    raise ValueError("Order pagination repeated an order ID")
                seen.add(key)
                orders.append(row)
            # Some responses report page length, others total length. An extra
            # empty-page request avoids making assumptions about that field.

    def read_equity_chart(self, project_id, backtest_id, count=10000):
        return self._read_ready("backtests/chart/read", {
            "projectId": project_id, "backtestId": backtest_id,
            "name": "Strategy Equity", "start": 0,
            "end": int(time.time()), "count": count})["chart"]


if __name__ == "__main__":
    print("authenticated:", QCClient().authenticate())
