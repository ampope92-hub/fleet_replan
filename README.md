# Line-Haul Owner-Driver Payroll

A line-haul operator still assembles the monthly pay run for its owner-drivers by hand in a spreadsheet. The agent gets one month's export in `/app/data`: `runs.csv` (every dispatched run with tracker hours), `drivers.csv` (drivers on the book), `tariff.json` (contracted rates, which change at renewal) and a README describing the columns. It also gets a Go module stub at `/app/payroll` and a spec, `SPEC.md`, giving the pay rules and report format. The agent must implement the module so that `go build -o payroll . && ./payroll` writes `/app/out/payroll.json` with each driver's pay components in pence, the count of unmatched runs and a grand total. The box is offline and only the Go standard library is available.

## What makes it hard

There is nothing to fit and nothing to search for. The difficulty is precision: the spec has nine rules, each with a plausible wrong reading right beside the correct one, and getting eight right still fails.

- Hours round **up** to the next quarter, not to the nearest. A value already on a quarter stays put.
- The first drop is part of the run, so a single-drop run pays nothing for drops.
- The distance band applies one rate to the whole run, not marginal rates across bands, and the boundary is "at or under".
- The weekly cap runs Monday to Sunday by start date. Runs settle in start-date order with ties broken by run id, and the run that crosses the cap is **split** between the two rates.
- A cancellation after dispatch pays a flat fee only. A cancellation before dispatch pays nothing and is not counted.
- Rows for drivers not on the book are dropped and counted, whatever their status.
- Fuel is a percentage of distance pay only.
- The long-run supplement starts **at** the threshold.
- Every rounding happens per run, on its own component, never on a total.

The generator plants rows on every one of these boundaries in the shipped month. The held-back month uses a different tariff and different drivers, so hard-coded figures fail there.

## How it's graded

Grading runs in a separate, offline verifier container. The verifier builds the module itself from the shipped `go.mod` plus the `.go` files under `/app/payroll`, as an unprivileged user with cgo off and no module downloads. It then runs the binary twice: once on the shipped month and once on a held-back month with a different tariff.

The expected output is computed during grading by an independent Python implementation, written from the spec without reference to the Go solution. Every figure for every driver must match exactly. There are no tolerances, because all values are integers and the JSON is parsed by key. Per month, the checks cover report shape, components summing to each driver's total, drivers summing to the grand total, `unmatched_runs`, and every driver's figures. Separate checks require `go.mod` and the shipped data files to be byte-identical to the issued copies.

Anti-cheat measures: while the binary runs, every compiler, interpreter and shell on the box (the Go toolchain, python, perl, awk, bash, sh) is closed to it by file mode, so the work cannot be handed off to another program. The held-back data and the tests cannot be read by the build user. Ten arms of the reference, each with one rule taken the wrong way, all score 0. Hard-coding the shipped month's figures also scores 0.

## Repository layout

- `instruction.md`: the task prompt given to the agent.
- `task.toml`: metadata, difficulty, solution and verification notes, and resource limits.
- `environment/`: the agent's container (`Dockerfile`), the shipped month (`data/`) and the Go module stub plus `SPEC.md` (`payroll/`).
- `solution/`: `solve.sh`, the reference Go implementation (`main.go`) and the seeded month generator (`generate_month.py`).
- `tests/`: verifier image and entrypoint (`Dockerfile`, `test.sh`), pytest checks (`test_outputs.py`), the independent Python payroll (`payroll_expected.py`), the held-back month (`holdout/`) and the pristine `go.mod` (`skeleton/`).

## Running it

Requires Docker and Harbor (`uv tool install harbor` or `pip install harbor`). From the repo root:

```
harbor run -p . -a oracle
```

This runs the reference solution through the verifier and should score reward 1. To try an agent instead:

```
harbor run -p . -a <agent> -m <model>
```

For example, `-a claude-code`.

---

Task design, data generators, reference solution and verifier by Audrey Pope.
