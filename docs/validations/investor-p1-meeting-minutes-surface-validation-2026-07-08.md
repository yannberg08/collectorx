# Investor P1 Meeting Minutes Surface Validation - 2026-07-08

Scope: `meeting-minutes` investor lens inside `investor-source-collectors`.

Goal: prove that meeting and collaboration Lake events can become structured
investment-avatar evidence without turning unrelated operational meetings into
Wiki facts.

Validated changes:

- `meeting-minutes` classifies roadshow minutes, research meetings,
  investment committee records, expert calls, earnings calls, decision points,
  risk discussions, and follow-up actions.
- `manifest.lens_surface_summary` and
  `investor_wiki_evidence.v1.coverage_summary.source_surface_summary` report:
  - expected and missing meeting surfaces
  - primary meeting surface counts
  - upstream collector counts
  - source platform counts
  - participant event/reference counts
  - meeting URL, attachment ref, and recording ref coverage
  - matched symbol event count
  - time coverage
- The lens remains downstream of generic meeting/collaboration collectors and
  does not write final Wiki pages directly.

Fixture coverage:

- `meeting-artifacts` local meeting-file event for roadshow minutes.
- `feishu` event for expert-call/research-meeting evidence.
- `dingtalk` collaboration event for investment committee and decision-point
  evidence.
- `wecom` meeting export event for earnings-call and recording-ref evidence.
- One unrelated team-building meeting, which is filtered out.

Validation commands:

```bash
.venv/bin/python -m py_compile skills/investor-source-collectors/scripts/investor_sources/classifier.py skills/investor-source-collectors/scripts/investor_sources/events.py skills/investor-source-collectors/tests/test_investor_sources.py
.venv/bin/python skills/investor-source-collectors/tests/test_investor_sources.py
```

Result:

- Local py_compile passed.
- `investor-source-collectors` test suite passed.

Remaining production gaps:

- Validate real Feishu, DingTalk, WeCom, and Tencent Meeting authorized
  artifacts.
- Normalize participant identities across platforms.
- Validate attachment and recording references without fetching unauthorized
  bodies.
- Backtest false positives against mixed enterprise collaboration data.
