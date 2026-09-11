"""A/B runtime checks for the three strongest Streamlit deployment shapes."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".firecrawl" / "ab-deploy-runtime.json"
HEALTH = "/_stcore/health"
VIETLOTT = "https://vietlott.vn/vi/trung-thuong/ket-qua-trung-thuong/winning-number-645"


def _fetch(url: str, timeout: float = 8.0) -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": "mega645-ab-deploy/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            headers = {key.lower(): value for key, value in response.headers.items()}
            return int(response.status), headers, response.read()
    except urllib.error.HTTPError as exc:
        headers = {key.lower(): value for key, value in exc.headers.items()} if exc.headers else {}
        return int(exc.code), headers, exc.read() if exc.fp else b""


def _wait_health(base: str, timeout_seconds: float = 45.0) -> dict[str, object]:
    started = time.perf_counter()
    last_error = "timeout"
    while time.perf_counter() - started < timeout_seconds:
        try:
            status, _headers, body = _fetch(base + HEALTH, timeout=2.5)
            elapsed_ms = round((time.perf_counter() - started) * 1000)
            if status == 200 and body.strip().lower() in {b"ok", b"ok\n"}:
                return {"ok": True, "status": status, "body": body.decode("utf-8", "replace").strip(), "ready_ms": elapsed_ms}
            last_error = f"status={status} body={body[:80]!r}"
        except Exception as exc:  # noqa: BLE001 - probe until timeout.
            last_error = str(exc)
        time.sleep(0.4)
    return {"ok": False, "error": last_error, "ready_ms": round((time.perf_counter() - started) * 1000)}


def _start_streamlit(port: int, extra: list[str]) -> subprocess.Popen[bytes]:
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(ROOT / "streamlit_app.py"),
        "--server.headless=true",
        f"--server.port={port}",
        *extra,
    ]
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )


def _stop(proc: subprocess.Popen[bytes]) -> str:
    if proc.poll() is not None:
        output = proc.stdout.read().decode("utf-8", "replace") if proc.stdout else ""
        return output[-4000:]
    if os.name == "nt":
        proc.send_signal(signal.CTRL_BREAK_EVENT)
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
    else:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
    output = proc.stdout.read().decode("utf-8", "replace") if proc.stdout else ""
    return output[-4000:]


def _probe_ui(base: str) -> dict[str, object]:
    status, _headers, body = _fetch(base + "/", timeout=8.0)
    text = body.decode("utf-8", "replace")
    return {
        "ok": status == 200 and ("streamlit" in text.lower() or "mega 6/45" in text.lower()),
        "status": status,
        "has_streamlit_marker": "streamlit" in text.lower(),
        "bytes": len(body),
    }


def variant_a() -> dict[str, object]:
    port = 8501
    proc = _start_streamlit(port, ["--server.address=0.0.0.0"])
    base = f"http://127.0.0.1:{port}"
    try:
        health = _wait_health(base)
        ui = _probe_ui(base) if health.get("ok") else {"ok": False, "error": "health-failed"}
        return {
            "id": "A",
            "name": "Streamlit Community Cloud equivalent",
            "command": "streamlit run streamlit_app.py --server.headless=true --server.port=8501 --server.address=0.0.0.0",
            "health": health,
            "ui": ui,
            "pass": bool(health.get("ok") and ui.get("ok")),
        }
    finally:
        logs = _stop(proc)
        variant_a.logs = logs  # type: ignore[attr-defined]


def variant_b() -> dict[str, object]:
    port = 8510
    proc = _start_streamlit(
        port,
        [
            "--server.address=0.0.0.0",
            "--browser.gatherUsageStats=false",
        ],
    )
    base = f"http://127.0.0.1:{port}"
    try:
        health = _wait_health(base)
        ui = _probe_ui(base) if health.get("ok") else {"ok": False, "error": "health-failed"}
        return {
            "id": "B",
            "name": "Render / Docker equivalent (explicit bind + custom port)",
            "command": f"streamlit run streamlit_app.py --server.headless=true --server.port={port} --server.address=0.0.0.0",
            "health": health,
            "ui": ui,
            "pass": bool(health.get("ok") and ui.get("ok")),
            "note": "Same Python server as Hugging Face Docker Spaces / Render web service. Docker Engine was not installed on this machine, so the image was not built.",
        }
    finally:
        logs = _stop(proc)
        variant_b.logs = logs  # type: ignore[attr-defined]


def variant_c() -> dict[str, object]:
    status, headers, body = _fetch(VIETLOTT, timeout=15.0)
    acao = headers.get("access-control-allow-origin")
    cors_open = acao in {"*", "https://stlite.net", "http://localhost"}
    return {
        "id": "C",
        "name": "stlite / Pyodide (in-browser Streamlit, GitHub Pages)",
        "vietlott_status": status,
        "access_control_allow_origin": acao,
        "official_bytes": len(body),
        "cors_allows_browser_python": cors_open,
        "pass": False,
        "reason": (
            "stlite runs Streamlit in WebAssembly. Browser Python uses fetch, so vietlott.vn "
            "must send Access-Control-Allow-Origin. Official page has no open CORS header, "
            "and JSONL writes cannot persist to GitHub. Rejected for this app."
        ),
    }


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    results = {
        "project": "vietlott-mega645",
        "python": sys.version.split()[0],
        "variants": [],
        "winner": None,
    }
    for factory in (variant_a, variant_b, variant_c):
        item = factory()
        results["variants"].append(item)
    passed = [item for item in results["variants"] if item.get("pass")]
    results["winner"] = "A" if any(item["id"] == "A" and item.get("pass") for item in passed) else (passed[0]["id"] if passed else None)
    results["winner_reason"] = (
        "A keeps Streamlit, deploys from GitHub with zero framework change, ships the local JSONL, "
        "avoids Vercel, and matches the runtime that MCP browser can test."
    )
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: results[key] for key in ("winner", "python")}, ensure_ascii=False, indent=2))
    for item in results["variants"]:
        print(f"{item['id']} pass={item.get('pass')} name={item['name']}")
    return 0 if results["winner"] == "A" else 1


if __name__ == "__main__":
    raise SystemExit(main())
