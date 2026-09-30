#!/usr/bin/env bash
set -euo pipefail

# Reference pay run. The rules are all in SPEC.md; the work is following each one exactly,
# in integers, and settling each driver's week in the stated order so the run that crosses
# the weekly cap is the right one. main.go next to this script is the implementation.
install -m 644 "$(dirname "$0")/main.go" /app/payroll/main.go
cd /app/payroll
go build -o payroll .
./payroll
