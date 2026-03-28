# Windows Setup Template

Use this reference as a portable checklist for adapting the skill to a real Windows machine.

## Typical path patterns

- Antigravity desktop app: `%USERPROFILE%\AppData\Local\Programs\Antigravity\Antigravity.exe`
- Antigravity CLI wrapper: `%USERPROFILE%\AppData\Local\Programs\Antigravity\bin\antigravity.cmd`
- Chrome executable: `C:\Program Files\Google\Chrome\Application\chrome.exe`
- Standalone browser profile: `%USERPROFILE%\.gemini\antigravity-browser-profile`
- Antigravity profile directory: `%USERPROFILE%\.antigravity`
- Antigravity tools directory: `%USERPROFILE%\.antigravity_tools`

## Endpoint expectations

- CDP endpoint: `http://127.0.0.1:9222/json/version`
- Live MCP endpoint: `http://127.0.0.1:55829/mcp`

Interpretation:

- `200 OK` from `/json/version` means the browser DevTools endpoint is live.
- `409 Conflict` from `/mcp` can still be acceptable when the MCP server is already holding an SSE stream open.
- If both endpoints stay down, keep using standalone mode instead of pretending the bridge is ready.

## Portable operating guidance

- Default workflow: standalone Chrome with the reusable profile directory.
- Optional workflow: live bridge probing only when bridge-only behavior matters.
- Primary reason: the standalone path is usually faster, cheaper in tokens, and easier to debug while still preserving real-browser and DOM-aware work.

## Known good expectations

- `probe_antigravity.py --json` should emit a compact standalone-first report.
- `capture_dom_evidence.py --json` should return:
  - `target_section`
  - `role_targets`
  - `dom_excerpt`
  - `screenshot_path`
  - `residual_risk`

## Adaptation checklist

1. Confirm Chrome is installed and reachable.
2. Confirm the standalone profile directory is writable.
3. Probe standalone mode first.
4. Probe bridge mode only if you truly need CDP or MCP behavior.
5. Replace local examples from private notes with your own discovered paths before documenting machine-specific setup elsewhere.
