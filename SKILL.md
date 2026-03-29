---
name: antigravity-websearch
description: Run Antigravity-style web research in a standalone browser-first workflow, using a real local Chrome profile, DOM-aware capture habits, and optional bridge probing only when explicitly needed. Use when the user asks for Antigravity web search, wants Antigravity-like browser automation without depending on the live `9222` or `55829` bridge, needs the local Antigravity install or Chrome path, or wants bounded DOM extraction and screenshots with better token efficiency.
---

# Antigravity Websearch

Treat this skill as a standalone-first adapter that keeps Antigravity's useful habits without making the live bridge mandatory.

This public version is Windows-first and intentionally avoids machine-specific absolute paths in the instructions.

Use it to do three things quickly:

- find the installed Antigravity app, Chrome binary, and reusable browser profile on the current machine
- drive a real browser workflow through standalone Chrome first, using DOM capture selectively instead of dumping everything
- probe the live bridge only when the user explicitly asks for the Antigravity bridge or when bridge-only behavior matters

Read [references/verified-local-setup.md](references/verified-local-setup.md) when you need the typical Windows path patterns, endpoint expectations, and a portable setup checklist.
Read [references/dom-evidence-contract.md](references/dom-evidence-contract.md) when you need a repeatable capture contract for DOM excerpts, role targeting, and screenshot evidence.

## Quick Start

1. Run `scripts/probe_antigravity.py`.
2. Treat the default result as the preferred path: standalone Chrome with the reusable `standalone_profile`.
3. Use bridge mode only if the user explicitly asked for the live Antigravity bridge or needs bridge-only artifacts.
4. If the user explicitly asked for a subagent or delegation, spawn one bounded research subagent for external facts while you keep local code and synthesis in the parent thread.
5. For actual evidence capture, use `scripts/capture_dom_evidence.py` so the result comes back as `target_section`, `role_targets`, `dom_excerpt`, `screenshot_path`, and `residual_risk`.

## Standalone Workflow

Run:

```powershell
@'
from pathlib import Path
import subprocess, sys
script = Path('scripts/probe_antigravity.py').resolve()
raise SystemExit(subprocess.call([sys.executable, str(script)]))
'@ | python -
```

This now defaults to `standalone` mode and stays cheap enough to use as a first step.

Interpretation rules:

- `standalone_ready=true` means local Chrome exists and the reusable standalone profile path is known.
- `standalone_profile_busy=true` means another Chrome process is already holding the reusable standalone profile, so a second persistent-context launch may fail until that holder exits.
- The default JSON is intentionally compact to reduce token waste in follow-up agents.
- Use `--verbose` only when you need extra path existence or running-state details.

## Bridge Workflow

Use bridge mode only when the user actually needs live Antigravity bridge behavior:

```powershell
@'
from pathlib import Path
import subprocess, sys
script = Path('scripts/probe_antigravity.py').resolve()
raise SystemExit(subprocess.call([sys.executable, str(script), '--mode', 'bridge', '--json']))
'@ | python -
```

If the user wants the app launched before the bridge probe, use:

```powershell
@'
from pathlib import Path
import subprocess, sys
script = Path('scripts/probe_antigravity.py').resolve()
raise SystemExit(subprocess.call([sys.executable, str(script), '--mode', 'bridge', '--launch', '--wait', '6', '--json']))
'@ | python -
```

- `cdp_ok=true` means the browser-side DevTools bridge is up.
- `mcp_ok=true` means the live MCP bridge answered.
- `launch_attempted=true` only means the app was started, not that the bridge is ready.
- If both bridge checks stay down, keep using standalone mode instead of pretending the bridge is live.

## DOM Capture Rules

Preserve the part of Antigravity that matters most: use a real browser and reason over DOM structure, not only text snapshots.

- Default contract: do not dump the entire DOM, do not lead with free-text scraping, and do not return a DOM-only claim without at least one screenshot when UI state matters.
- Prefer targeted DOM extraction over full-page DOM dumps.
- Prefer role-aware targeting when possible, such as buttons, links, inputs, and obvious interactive regions, instead of brittle free-text scraping.
- Treat closely related input roles as the same family when the task is about text entry. In practice, `textbox`, `combobox`, and `searchbox` should satisfy the same search-input intent unless the user explicitly wants the ARIA distinction preserved.
- When multiple role families are requested, preserve at least one candidate from each requested family when the page exposes one, before filling the remaining slots with extra matches from the busiest role.
- Ask for a section, selector family, or interaction goal instead of "read the whole page".
- Pair DOM data with a screenshot when layout or state matters.
- Treat full DOM, console logs, and recording artifacts as escalation steps because they are token-heavy.
- When the DOM is large, reduce it into a short markdown-like structural summary before sending it to another agent or model.

Use this evidence ladder by default:

1. Narrow DOM or role-based excerpt
2. Short structural summary
3. Screenshot
4. Console logs
5. Video or long interaction recording only when proof of multi-step behavior matters

Use this execution order by default:

1. Define the target section or task boundary
2. Identify likely interactive roles such as button, link, textbox, combobox, dialog, or menuitem
3. Extract only the minimum DOM slice needed for the task
4. Save one screenshot that proves the state you are describing
5. Escalate to logs or video only if the first four are insufficient

Good prompts:

- `네이버 뉴스 헤드라인 영역만 DOM 기준으로 뽑아줘`
- `검색창 입력과 첫 결과 클릭까지 확인하고 스크린샷 한 장만 남겨줘`
- `로그인 상태에서 보이는 특정 패널만 확인해줘`

Minimum acceptable result shape for UI-facing tasks:

- `target_section`: what part of the page was inspected
- `role_targets`: which interactive roles were used to narrow the search
- `dom_excerpt`: only the relevant structural excerpt or summary
- `screenshot_path`: one concrete screenshot artifact
- `residual_risk`: what still could be wrong

## Logged-in Blogs and Frame Pages

Use these as narrow fallback habits, not as the default strategy for every site.

- On logged-in services, confirm session identity markers first when route ambiguity matters. Good markers include `nickname`, account email, `내 블로그`, `blogId`, or `domainId`.
- If the outer page is mostly a wrapper or frameset, inspect it for a real content target such as `iframe`, `mainFrame`, or a direct `src` that points to the actual content view, then follow that URL.
- If a desktop route opens a single post but the user's intent is clearly "recent posts" or "post list", prefer the list route over the single-post route before retrying extraction.
- For Naver Blog specifically, `MyBlog.naver` may open the latest post view while the real list content lives under `PostList.naver?blogId=<id>` or the mobile blog home.
- Use mobile fallback only when it better matches the user's intent, such as showing a recent-post list clearly, and record that choice in `residual_risk` when it matters.

## Evidence Capture Script

Use this script when you need a cheap standalone artifact bundle instead of a full bridge session:

```powershell
@'
from pathlib import Path
import subprocess, sys
script = Path('scripts/capture_dom_evidence.py').resolve()
raise SystemExit(subprocess.call([
    sys.executable,
    str(script),
    '--url', 'https://www.naver.com',
    '--section', 'top search area',
    '--roles', 'textbox,button,link',
    '--json',
]))
'@ | python -
```

Default behavior:

- one Chrome run for both screenshot and DOM capture
- compact JSON output aligned to the minimum acceptable result shape
- standalone profile reuse for better speed on repeated runs

## Interactive App Notes

For authenticated creative apps and other app-shell products:

- Confirm whether you are in the real app shell or only on a marketing or about page before concluding that an action is missing.
- If a control exists visually but role-based selectors are unstable, fall back to a short DOM-text marker that is actually rendered in the button, then click it in the same browser session.
- Prefer one uninterrupted session for `new project -> prompt -> generate` flows so state is not lost between steps.

## Subagent Lane

Only use subagents when the user explicitly asked for delegation, subagents, or parallel agent work.

When a subagent is authorized, spawn exactly one bounded research subagent and keep the write scope in the parent thread.

Recommended delegation pattern:

1. Parent agent probes Antigravity locally.
2. Parent agent defines a narrow research question.
3. Research subagent gathers external facts and URLs only.
4. Parent agent integrates findings with local code or repo context.

Preferred subagent choices:

- Use `docs-researcher` for documentation-backed or source-heavy research.
- Use `default` only if the task is general web synthesis and no specialist role fits better.

Use a prompt shaped like this:

```text
Use the local antigravity-websearch skill checkout.
Research only the external question below and return source-backed findings with direct URLs.
Do not edit files. Do not analyze local code unless the parent passes a specific file.
Question: <bounded web question>
```

If the live Antigravity probes failed, tell the user the subagent is using normal web search as a fallback lane rather than an active Antigravity bridge.

## Typical Windows Paths

On many Windows installs, the likely paths are:

- app executable: `%USERPROFILE%\AppData\Local\Programs\Antigravity\Antigravity.exe`
- CLI wrapper: `%USERPROFILE%\AppData\Local\Programs\Antigravity\bin\antigravity.cmd`
- Chrome executable: `C:\Program Files\Google\Chrome\Application\chrome.exe`
- standalone profile: `%USERPROFILE%\.gemini\antigravity-browser-profile`
- app profile: `%USERPROFILE%\.antigravity`
- tools profile: `%USERPROFILE%\.antigravity_tools`

Do not hard-code macOS Chrome launcher paths from external examples when running in this workspace. Use the local Windows install first.

## Notes

- The user supplied prior evidence that the live bridge can expose `http://127.0.0.1:9222/json/version` and `http://127.0.0.1:55829/mcp`.
- The user also highlighted why Antigravity is valuable: real browser control, DOM-centered understanding, interaction-based search, and artifact-backed verification.
- This standalone-first skill keeps those habits where possible, while avoiding live bridge dependency as the default path.
- Do not encode speculative internal model names, private tool IDs, or JavaScript execution policies into this skill unless an official source confirms them.
- If the live ports are closed during the current run, report that concretely and continue with standalone behavior instead of claiming success.
