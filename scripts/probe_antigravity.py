#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def home_path() -> Path:
    user_profile = os.environ.get("USERPROFILE")
    return Path(user_profile) if user_profile else Path.home()


def chrome_candidates() -> list[Path]:
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("PROGRAMFILES", "")
    return [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(local_app_data) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(program_files) / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]


def first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path and path.exists():
            return path
    return None


def candidate_paths() -> dict[str, Path]:
    home = home_path()
    app_root = home / "AppData" / "Local" / "Programs" / "Antigravity"
    standalone_profile = home / ".gemini" / "antigravity-browser-profile"
    chrome_path = first_existing(chrome_candidates())
    return {
        "app_root": app_root,
        "app_exe": app_root / "Antigravity.exe",
        "cli_cmd": app_root / "bin" / "antigravity.cmd",
        "profile_dir": home / ".antigravity",
        "tools_dir": home / ".antigravity_tools",
        "chrome_exe": chrome_path or Path(""),
        "standalone_profile": standalone_profile,
    }


def probe_socket(host: str, port: int, timeout: float) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        try:
            sock.connect((host, port))
        except OSError:
            return False
    return True


def probe_http(url: str, timeout: float, include_body: bool) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "codex-antigravity-probe"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload: dict[str, Any] = {
                "ok": True,
                "status": response.getcode(),
            }
            if include_body:
                payload["body_preview"] = response.read(400).decode("utf-8", errors="replace")
            return payload
    except urllib.error.HTTPError as exc:
        payload = {
            "ok": exc.code in {200, 204, 409},
            "status": exc.code,
            "error": str(exc),
        }
        if include_body:
            payload["body_preview"] = exc.read(400).decode("utf-8", errors="replace")
        return payload
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "status": None,
            "error": str(exc),
        }


def process_running(image_name: str) -> bool:
    try:
        completed = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {image_name}"],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:  # noqa: BLE001
        return False
    return image_name in completed.stdout


def launch_antigravity(app_exe: Path) -> bool:
    if not app_exe.exists():
        return False
    try:
        subprocess.Popen([str(app_exe)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:  # noqa: BLE001
        return False
    return True


def build_standalone_report(paths: dict[str, Path], verbose: bool) -> dict[str, Any]:
    chrome_exe = paths["chrome_exe"]
    report: dict[str, Any] = {
        "mode": "standalone",
        "summary": {
            "standalone_ready": bool(chrome_exe),
        },
        "paths": {
            "chrome_exe": str(chrome_exe) if chrome_exe else "",
            "standalone_profile": str(paths["standalone_profile"]),
        },
    }
    if verbose:
        report["summary"]["chrome_running"] = process_running("chrome.exe")
        report["paths"]["app_exe"] = str(paths["app_exe"])
        report["exists"] = {name: path.exists() for name, path in paths.items() if str(path)}
    return report


def build_bridge_report(paths: dict[str, Path], timeout: float, verbose: bool) -> dict[str, Any]:
    include_body = verbose
    cdp_http = probe_http("http://127.0.0.1:9222/json/version", timeout, include_body)
    mcp_http = probe_http("http://127.0.0.1:55829/mcp", timeout, include_body)
    return {
        "mode": "bridge",
        "summary": {
            "bridge_ready": cdp_http.get("ok", False) or mcp_http.get("ok", False),
            "cdp_ok": cdp_http.get("ok", False),
            "mcp_ok": mcp_http.get("ok", False),
            "app_running": process_running("Antigravity.exe"),
        },
        "ports": {
            "cdp_9222_open": probe_socket("127.0.0.1", 9222, timeout),
            "mcp_55829_open": probe_socket("127.0.0.1", 55829, timeout),
        },
        "http": {
            "cdp_json_version": cdp_http,
            "live_mcp": mcp_http,
        },
        "paths": {
            "app_exe": str(paths["app_exe"]),
            "cli_cmd": str(paths["cli_cmd"]),
        },
    }


def build_report(mode: str, timeout: float, verbose: bool) -> dict[str, Any]:
    paths = candidate_paths()
    standalone_report = build_standalone_report(paths, verbose)
    if mode == "standalone":
        return standalone_report

    bridge_report = build_bridge_report(paths, timeout, verbose)
    if mode == "bridge":
        return bridge_report

    combined = standalone_report
    combined["mode"] = "auto"
    combined["summary"]["bridge_ready"] = bridge_report["summary"]["bridge_ready"]
    combined["bridge"] = bridge_report
    return combined


def print_human(report: dict[str, Any], launch_attempted: bool) -> None:
    print("Antigravity probe")
    print(f"mode={report['mode']}")
    print(f"launch_attempted={str(launch_attempted).lower()}")
    print("")
    summary = report.get("summary", {})
    for key in sorted(summary):
        print(f"- {key}: {str(summary[key]).lower() if isinstance(summary[key], bool) else summary[key]}")
    print("")
    for key, value in report.get("paths", {}).items():
        if value:
            print(f"- {key}: {value}")
    bridge = report.get("bridge")
    if bridge:
        print("")
        print("Bridge")
        for key in sorted(bridge["summary"]):
            value = bridge["summary"][key]
            print(f"- {key}: {str(value).lower() if isinstance(value, bool) else value}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe the local Antigravity setup.")
    parser.add_argument(
        "--mode",
        choices=("standalone", "bridge", "auto"),
        default="standalone",
        help="Choose standalone-first or explicit bridge probing.",
    )
    parser.add_argument("--launch", action="store_true", help="Launch Antigravity.exe before bridge probing.")
    parser.add_argument("--wait", type=float, default=4.0, help="Seconds to wait after launch.")
    parser.add_argument("--timeout", type=float, default=0.35, help="Per-bridge-probe timeout in seconds.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of human-readable output.")
    parser.add_argument("--verbose", action="store_true", help="Include extra existence and body-preview details.")
    args = parser.parse_args()

    launch_attempted = False
    if args.launch and args.mode in {"bridge", "auto"}:
        paths = candidate_paths()
        launch_attempted = launch_antigravity(paths["app_exe"])
        if launch_attempted:
            time.sleep(max(args.wait, 0))

    report = build_report(args.mode, args.timeout, args.verbose)
    if args.json:
        json.dump(
            {"launch_attempted": launch_attempted, **report},
            sys.stdout,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        sys.stdout.write("\n")
    else:
        print_human(report, launch_attempted)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
