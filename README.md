# antigravity-websearch

Standalone-first Codex skill for Antigravity-style browser research on Windows.

This repository packages the skill as a portable public checkout:

- `SKILL.md`: the main skill instructions
- `scripts/probe_antigravity.py`: lightweight local setup and bridge probe
- `scripts/capture_dom_evidence.py`: bounded DOM excerpt plus screenshot capture
- `references/`: reusable guidance for evidence capture and Windows setup
- `agents/openai.yaml`: optional agent metadata

## What it is for

Use this skill when you want Antigravity-like browser-first workflows without depending on a live bridge by default.

The main design choices are:

- standalone Chrome first
- live bridge only when explicitly needed
- small DOM excerpts instead of full dumps
- screenshot-backed evidence for UI claims

Recent practical improvements:

- standalone probe now exposes `standalone_profile_busy` so profile-lock failures are visible before a second persistent browser launch crashes
- interactive app runs are documented with a bias toward staying in one session for `new project -> prompt -> generate`
- public guidance now calls out that some products first land on a marketing or about page before the authenticated app shell

## Quick start

From the repository root:

```powershell
@'
from pathlib import Path
import subprocess, sys
script = Path('scripts/probe_antigravity.py').resolve()
raise SystemExit(subprocess.call([sys.executable, str(script), '--json']))
'@ | python -
```

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

## Requirements

- Windows
- Python 3.10+
- Google Chrome installed
- Optional Antigravity desktop install if you want bridge probing

## Notes

- The public package intentionally removes machine-specific private paths from the skill instructions.
- The probe and capture scripts still assume a Windows-style Chrome installation pattern.
- Output defaults to `artifacts/` under the current working directory.
- For authenticated browser apps, check whether you are in the real app shell before deciding a control is missing.
