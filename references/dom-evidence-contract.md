# DOM Evidence Contract

Use this contract for browser-facing tasks when token efficiency and verifiable evidence both matter.

## Decision rule

- Default to a narrow section, not the full page.
- Default to role-based targeting, not free-text scraping.
- Default to one screenshot artifact, not DOM-only claims.
- Treat `textbox`, `combobox`, and `searchbox` as one input-role family unless the task explicitly requires the exact ARIA role.
- When the caller asks for multiple role families, keep one representative from each family when available before adding extra buttons or links.

## Required fields

- `target_section`
  - Example: `네이버 홈 상단 검색 영역`
- `role_targets`
  - Example: `textbox, button, link`
- `dom_excerpt`
  - Include only the minimum structure needed to support the claim.
- `screenshot_path`
  - Save one screenshot that proves the rendered state.
- `residual_risk`
  - State what was not verified.

## Good pattern

1. Find the section boundary first.
2. Narrow to interactive roles.
3. Extract or summarize only the local DOM slice.
4. Capture one screenshot.
5. Report the result in the required fields.

## Avoid

- Full-page DOM dumps by default
- Text-only claims about layout or interaction state
- Selector fishing across the entire page without a section boundary
- Console logs or video unless the task requires deeper proof

## Example result

```text
target_section: 네이버 홈 상단 검색 영역
role_targets: textbox, button
dom_excerpt: search form wrapper, input textbox, submit button, quick-link icon row
screenshot_path: artifacts/naver-dom-capture/naver.png
residual_risk: autocomplete dropdown interaction is not verified
```
