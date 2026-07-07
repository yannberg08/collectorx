# First Investor Loop

This document records the first complete CollectorX -> investor wiki loop.

## Goal

Prove a minimal, testable data path:

```text
Tonghuashun CSV
  -> ths-portfolio parser
  -> collectorx.event.v1 trade events
  -> lake/ths-portfolio/events.jsonl
  -> deterministic investor organizer
  -> wiki/vertical/investor/*.md
  -> investor_maturity.json
```

This is intentionally conservative. A trade record proves that the user acted;
it does not prove why the user acted.

## Run

```bash
python3 tools/run_first_investor_loop.py \
  --input-csv examples/fixtures/ths-portfolio.sample.csv \
  --out-dir .tmp/first-investor-loop
```

## Outputs

| File | Meaning |
| --- | --- |
| `lake/ths-portfolio/events.jsonl` | CollectorX trade events |
| `wiki/vertical/investor/record-review/决策日志.md` | Trade evidence table |
| `wiki/vertical/investor/risk-portfolio/组合约束.md` | Preliminary amount/concentration clues |
| `wiki/vertical/investor/competence-circle/公司能力圈.md` | Companies seen in trade records |
| `wiki/vertical/investor/decision-framework/仓位决策.md` | Trade-size clues |
| `wiki/vertical/investor_maturity.json` | Conservative maturity summary |

## Validation

The smoke test is included in `tools/validate_project.py`, so this loop runs
whenever you run:

```bash
bash test_collectors.sh
```

## Next Data Needed

To move from action evidence to a real investor avatar, add:

- holding snapshots
- total assets or portfolio weights
- buy/sell reasons
- research notes
- review notes
- investment conversations
