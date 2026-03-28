#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


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


def default_profile_dir() -> Path:
    return home_path() / ".gemini" / "antigravity-browser-profile"


def default_output_dir() -> Path:
    return Path.cwd() / "artifacts" / "dom-evidence"


def slugify(value: str) -> str:
    lowered = value.lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", lowered)
    return cleaned.strip("-") or "page"


SECTION_HINTS: dict[str, tuple[str, ...]] = {
    "search": ("search", "query", "검색", "검색창", "search_area", "search-btn"),
    "top": ("top", "header", "gnb", "상단", "헤더"),
    "login": ("login", "signin", "로그인", "nidlogin"),
    "news": ("news", "뉴스"),
    "menu": ("menu", "gnb", "메뉴", "nav"),
}

IGNORE_LABEL_TOKENS = {
    "is",
    "btn",
    "button",
    "link",
    "item",
    "module",
    "fadein",
    "wrap",
    "area",
    "box",
    "inner",
    "type",
    "naver",
    "ico",
    "icon",
    "blind",
    "text",
    "view",
    "motion",
    "ly",
    "nx",
    "na",
    "sb",
    "kh",
    "ke",
}

TOKEN_LABEL_MAP = {
    "kbd": "keyboard",
    "autocomplete": "autocomplete",
    "nautocomplete": "autocomplete",
    "close": "close",
    "help": "help",
    "query": "query",
    "search": "search",
    "retry": "retry",
    "keywords": "keywords",
    "delall": "clear all",
    "login": "login",
}

ROLE_EQUIVALENTS: dict[str, tuple[str, ...]] = {
    "textbox": ("textbox", "combobox", "searchbox"),
    "combobox": ("combobox", "textbox", "searchbox"),
    "searchbox": ("searchbox", "textbox", "combobox"),
}


def expand_section_tokens(section: str) -> list[str]:
    raw_tokens = [token.strip().lower() for token in re.split(r"[\s/_-]+", section) if token.strip()]
    expanded: list[str] = []
    for token in raw_tokens:
        expanded.append(token)
        for key, aliases in SECTION_HINTS.items():
            if token == key or token in aliases:
                expanded.extend(aliases)
    seen: set[str] = set()
    ordered: list[str] = []
    for token in expanded:
        if token not in seen:
            seen.add(token)
            ordered.append(token)
    return ordered


def normalize_label_candidate(value: str) -> str:
    value = re.sub(r"[_\-]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def structural_label_from_value(value: str) -> str:
    pieces = [piece for piece in re.split(r"[^a-zA-Z0-9가-힣]+", value.lower()) if piece]
    normalized: list[str] = []
    for piece in pieces:
        mapped = TOKEN_LABEL_MAP.get(piece, piece)
        if mapped in IGNORE_LABEL_TOKENS:
            continue
        if len(mapped) <= 1:
            continue
        normalized.append(mapped)
    deduped: list[str] = []
    for token in normalized:
        if token not in deduped:
            deduped.append(token)
    return " ".join(deduped[:3]).strip()


def fallback_label_from_attrs(attrs: dict[str, str]) -> str:
    primary_candidates = [
        attrs.get("aria-label", ""),
        attrs.get("placeholder", ""),
        attrs.get("title", ""),
        attrs.get("value", ""),
        attrs.get("name", ""),
    ]
    structural_candidates = [attrs.get("id", "")]
    classes = attrs.get("class", "")
    if classes:
        structural_candidates.extend(classes.split())
    for candidate in primary_candidates:
        cleaned = normalize_label_candidate(candidate)
        if not cleaned:
            continue
        if cleaned.lower() in {"button", "link", "textbox"}:
            continue
        if re.search(r"[a-zA-Z가-힣]", cleaned):
            return cleaned[:80]
    for candidate in structural_candidates:
        structural = structural_label_from_value(candidate)
        if structural:
            return structural[:80]
    return ""


def role_variants(role: str) -> tuple[str, ...]:
    normalized = role.strip().lower()
    return ROLE_EQUIVALENTS.get(normalized, (normalized,))


def role_matches_requested(actual_role: str, requested_role: str) -> bool:
    return actual_role in role_variants(requested_role)


def expand_role_targets(roles: list[str]) -> set[str]:
    expanded: set[str] = set()
    for role in roles:
        expanded.update(role_variants(role))
    return expanded


def semantic_role(tag: str, attrs: dict[str, str]) -> str | None:
    explicit_role = attrs.get("role", "").strip().lower()
    if explicit_role:
        return explicit_role
    if tag == "a":
        return "link"
    if tag == "button":
        return "button"
    if tag == "input":
        input_type = attrs.get("type", "text").strip().lower()
        if input_type in {"text", "search", "email", "url", "tel", "password"}:
            return "textbox"
        if input_type in {"submit", "button", "reset"}:
            return "button"
    if tag == "textarea":
        return "textbox"
    if tag == "select":
        return "combobox"
    return None


class InteractiveSummaryParser(HTMLParser):
    def __init__(self, role_targets: set[str], section_tokens: list[str], limit: int) -> None:
        super().__init__(convert_charrefs=True)
        self.role_targets = role_targets
        self.section_tokens = section_tokens
        self.limit = limit
        self.collection_limit = max(limit * 6, 24)
        self.current: list[dict[str, Any]] = []
        self.matches: list[dict[str, str]] = []
        self.fallback_matches: list[dict[str, str]] = []
        self.seen_candidates: set[str] = set()
        self.context_stack: list[str] = []

    def _record_candidate(self, top: dict[str, Any]) -> None:
        if len(self.matches) + len(self.fallback_matches) >= self.collection_limit:
            return
        text = " ".join(top.get("text_parts", [])).strip()
        label = top.get("label") or text or "(unlabeled)"
        lowered = f"{label} {text} {top.get('combined_blob', '')}".lower()
        section_ok = top.get("section_hit") or not self.section_tokens or any(token in lowered for token in self.section_tokens)
        candidate_key = f"{top['role']}: {label[:80]}"
        if candidate_key in self.seen_candidates:
            return
        candidate = {"role": top["role"], "label": label[:80]}
        if section_ok:
            self.seen_candidates.add(candidate_key)
            self.matches.append(candidate)
            return
        if len(self.fallback_matches) < self.collection_limit:
            self.seen_candidates.add(candidate_key)
            self.fallback_matches.append(candidate)

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = {key: (value or "") for key, value in attrs_list}
        attr_blob = " ".join(
            part
            for part in [
                attrs.get("id", ""),
                attrs.get("class", ""),
                attrs.get("name", ""),
                attrs.get("placeholder", ""),
                attrs.get("aria-label", ""),
                attrs.get("title", ""),
            ]
            if part
        ).lower()
        parent_blob = " ".join(self.context_stack[-4:])
        combined_blob = f"{parent_blob} {attr_blob}".strip()
        self.context_stack.append(attr_blob)
        role = semantic_role(tag, attrs)
        if not role or role not in self.role_targets:
            self.current.append({"active": False, "tag": tag})
            return
        label = fallback_label_from_attrs(attrs)
        section_hit = not self.section_tokens or any(token in combined_blob for token in self.section_tokens)
        self.current.append(
            {
                "active": True,
                "tag": tag,
                "role": role,
                "label": label.strip(),
                "section_hit": section_hit,
                "combined_blob": combined_blob,
                "text_parts": [],
            }
        )
        if tag in {"input"}:
            top = self.current.pop()
            self.context_stack.pop()
            self._record_candidate(top)

    def handle_data(self, data: str) -> None:
        if not self.current:
            return
        top = self.current[-1]
        if top.get("active"):
            text = " ".join(data.split())
            if text:
                top["text_parts"].append(text)

    def handle_endtag(self, tag: str) -> None:
        if not self.current:
            return
        top = self.current.pop()
        if self.context_stack:
            self.context_stack.pop()
        if not top.get("active") or top.get("tag") != tag:
            return
        self._record_candidate(top)


def run_chrome(chrome_exe: Path, args: list[str], timeout_ms: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(chrome_exe), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=max(1, timeout_ms // 1000),
    )


def capture_dom_and_screenshot(
    chrome_exe: Path,
    profile_dir: Path,
    url: str,
    output_path: Path,
    timeout_ms: int,
    virtual_time_budget_ms: int,
) -> subprocess.CompletedProcess[str]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    args = [
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--window-size=1440,2200",
        f"--virtual-time-budget={virtual_time_budget_ms}",
        f"--user-data-dir={profile_dir}",
        f"--screenshot={output_path}",
        "--dump-dom",
        url,
    ]
    return run_chrome(chrome_exe, args, timeout_ms)


def format_candidate(candidate: dict[str, str]) -> str:
    return f"{candidate['role']}: {candidate['label']}"


def build_excerpt(dom_text: str, roles: list[str], section: str, limit: int) -> tuple[str, int, bool]:
    parser = InteractiveSummaryParser(expand_role_targets(roles), expand_section_tokens(section), limit)
    parser.feed(dom_text)
    selected: list[dict[str, str]] = []
    used_keys: set[str] = set()
    used_section_fallback = False

    def add_first_matching(pool: list[dict[str, str]], requested_role: str) -> bool:
        for candidate in pool:
            candidate_key = format_candidate(candidate)
            if candidate_key in used_keys:
                continue
            if not role_matches_requested(candidate["role"], requested_role):
                continue
            used_keys.add(candidate_key)
            selected.append(candidate)
            return True
        return False

    for role in roles:
        if len(selected) >= limit:
            break
        if add_first_matching(parser.matches, role):
            continue
        if add_first_matching(parser.fallback_matches, role):
            used_section_fallback = True

    for pool, fallback_used in ((parser.matches, False), (parser.fallback_matches, True)):
        for candidate in pool:
            if len(selected) >= limit:
                break
            candidate_key = format_candidate(candidate)
            if candidate_key in used_keys:
                continue
            used_keys.add(candidate_key)
            selected.append(candidate)
            used_section_fallback = used_section_fallback or fallback_used
        if len(selected) >= limit:
            break

    if selected:
        return " | ".join(format_candidate(candidate) for candidate in selected), len(selected), used_section_fallback
    if parser.fallback_matches:
        return " | ".join(format_candidate(candidate) for candidate in parser.fallback_matches[:limit]), min(len(parser.fallback_matches), limit), True
    return "", 0, False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture standalone browser evidence with a compact DOM excerpt and screenshot.")
    parser.add_argument("--url", required=True, help="Target URL")
    parser.add_argument("--section", default="page", help="Target page section or task boundary")
    parser.add_argument("--roles", default="textbox,button,link", help="Comma-separated role targets")
    parser.add_argument("--out-dir", default=str(default_output_dir()), help="Output directory for screenshot and optional artifacts")
    parser.add_argument("--profile-dir", default=str(default_profile_dir()), help="Chrome user data dir")
    parser.add_argument("--timeout-ms", type=int, default=12000, help="Per Chrome invocation timeout in ms")
    parser.add_argument("--virtual-time-budget-ms", type=int, default=2500, help="Chrome virtual time budget in ms")
    parser.add_argument("--dom-limit", type=int, default=6, help="Max number of matched interactive elements")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    parser.add_argument("--keep-dom-file", action="store_true", help="Persist raw DOM dump to disk")
    parser.add_argument("--verbose", action="store_true", help="Include extra runtime and environment details")
    return parser.parse_args()


def needs_retry(completed: subprocess.CompletedProcess[str], screenshot_path: Path) -> bool:
    if completed.returncode != 0:
        return True
    if not completed.stdout.strip():
        return True
    if not screenshot_path.exists():
        return True
    return False


def main() -> int:
    args = parse_args()
    chrome_exe = first_existing(chrome_candidates())
    if not chrome_exe:
        print("Chrome executable not found.", file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    profile_dir = Path(args.profile_dir)
    parsed = urlparse(args.url)
    page_slug = slugify(parsed.netloc or "page")
    section_slug = slugify(args.section)
    screenshot_path = out_dir / f"{page_slug}-{section_slug}.png"
    dom_path = out_dir / f"{page_slug}-{section_slug}.html"
    roles = [role.strip() for role in args.roles.split(",") if role.strip()]
    retry_profile_dir: Path | None = None

    start = time.perf_counter()
    combined = capture_dom_and_screenshot(
        chrome_exe=chrome_exe,
        profile_dir=profile_dir,
        url=args.url,
        output_path=screenshot_path,
        timeout_ms=args.timeout_ms,
        virtual_time_budget_ms=args.virtual_time_budget_ms,
    )
    if needs_retry(combined, screenshot_path):
        retry_profile_dir = Path(tempfile.mkdtemp(prefix="ag-dom-", dir=str(out_dir)))
        combined = capture_dom_and_screenshot(
            chrome_exe=chrome_exe,
            profile_dir=retry_profile_dir,
            url=args.url,
            output_path=screenshot_path,
            timeout_ms=args.timeout_ms,
            virtual_time_budget_ms=args.virtual_time_budget_ms,
        )
    elapsed_ms = round((time.perf_counter() - start) * 1000.0, 3)

    dom_text = combined.stdout.strip()
    dom_excerpt, element_count, used_section_fallback = build_excerpt(dom_text, roles, args.section, args.dom_limit)
    if args.keep_dom_file and dom_text:
        dom_path.write_text(dom_text, encoding="utf-8")

    residual_risk_parts: list[str] = []
    if combined.returncode != 0 or not screenshot_path.exists():
        residual_risk_parts.append("screenshot_capture_failed")
    if not dom_text:
        residual_risk_parts.append("dom_dump_empty_or_blocked")
    if dom_text and not dom_excerpt:
        residual_risk_parts.append("section_or_roles_not_located")
    if used_section_fallback:
        residual_risk_parts.append("section_fallback_used")

    result = {
        "target_section": args.section,
        "role_targets": roles,
        "dom_excerpt": dom_excerpt,
        "screenshot_path": str(screenshot_path),
        "residual_risk": residual_risk_parts or ["low"],
    }

    if args.verbose:
        result["url"] = args.url
        result["dom_available"] = bool(dom_text)
        result["matched_elements"] = element_count
        result["screenshot_exists"] = screenshot_path.exists()
        result["screenshot_bytes"] = screenshot_path.stat().st_size if screenshot_path.exists() else 0
        result["chrome_exe"] = str(chrome_exe)
        result["standalone_profile"] = str(retry_profile_dir or profile_dir)
        result["elapsed_ms"] = elapsed_ms
        result["returncode"] = combined.returncode
        result["used_retry_profile"] = bool(retry_profile_dir)

    if args.keep_dom_file and dom_text:
        result["dom_path"] = str(dom_path)

    if args.json:
        json.dump(result, sys.stdout, ensure_ascii=False, separators=(",", ":"))
        sys.stdout.write("\n")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))

    if retry_profile_dir:
        shutil.rmtree(retry_profile_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
