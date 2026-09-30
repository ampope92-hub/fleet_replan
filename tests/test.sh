#!/bin/bash

# Verifier entrypoint. Runs in the verifier container, not the agent's, and sees only the paths
# declared in `artifacts`. All tooling is baked into tests/Dockerfile; nothing is fetched here.

set -uo pipefail

mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

# Only stdout survives into the feedback bundle, so a script that dies on stderr dies invisibly.
exec 2>&1

as_runner() {
  setpriv --clear-groups --no-new-privs --reuid runner --regid runner "$@"
}

# Close the verifier's own code and the held-back month to the build user before anything
# untrusted runs. /logs/verifier goes with them: agent code has no business creating files beside
# the reward, even though root's final write would win.
chmod 700 /tests 2>/dev/null || true
chmod 700 /logs/verifier 2>/dev/null || true
if as_runner bash -c 'test -r /tests/test_outputs.py || ls /opt/holdout' >/dev/null 2>&1; then
  echo "FATAL: /tests or the held-back month is still reachable by the unprivileged build user."
  echo 0 > /logs/verifier/reward.txt
  exit 0
fi
echo "verifier files closed to the unprivileged build user"

# Keep the agent's export exactly as collected; the tests compare it with the shipped copy.
rm -rf /opt/agent_data
cp -a /app/data /opt/agent_data
chown -R root:root /opt/agent_data
chmod -R go-rwx /opt/agent_data

# The module is assembled from the shipped go.mod and the .go files the agent left under
# /app/payroll, and nothing else: no binary the agent built, no other file. The collected go.mod
# is compared with the shipped one and the result recorded for the tests, since the instruction
# says to leave it alone.
BUILD=/opt/build
rm -rf "$BUILD"
mkdir -p "$BUILD"
cp /tests/skeleton/go.mod "$BUILD/go.mod"
if cmp -s /app/payroll/go.mod /tests/skeleton/go.mod; then
  echo ok > /opt/gomod_check.txt
else
  echo changed > /opt/gomod_check.txt
  echo "go.mod differs from the shipped copy"
fi
chmod 600 /opt/gomod_check.txt
while IFS= read -r -d '' f; do
  mkdir -p "$BUILD/$(dirname "$f")"
  cp "/app/payroll/$f" "$BUILD/$f"
done < <(cd /app/payroll && find . -type f -name '*.go' -print0 2>/dev/null)
find "$BUILD" -type f -exec touch {} +
chown -R runner:runner "$BUILD"
echo "module assembled from $(find "$BUILD" -name '*.go' | wc -l) .go file(s) and the shipped go.mod"

# Every compiler and interpreter on the box, by real path. Open to the build user while the
# module builds, closed to it while the built binary runs, so the pay run cannot be handed to
# python, perl or the Go toolchain at run time. Root is unaffected; bash is not touched because
# Harbor collects the logs with it.
# The shells are on the list as well, so a program cannot hand the work to a bash script it
# carries. They are closed only for the seconds the binary runs and reopened straight after,
# and the trap reopens them if this script dies in between, so log collection is never left
# without a shell. This script itself is already running and root besides.
# The Go toolchain's own compiler, linker and helpers under pkg/tool are on the list too, not
# just the go wrapper, so generated code cannot be compiled at run time by calling them directly.
TOOLS="$( { for t in python3 python3.13 pip perl awk mawk go gofmt gcc cc bash sh dash; do
             p="$(command -v "$t" 2>/dev/null)" && readlink -f "$p"; done
           find /usr/local/go/bin /usr/local/go/pkg/tool -type f -perm /111 2>/dev/null; } | sort -u)"
close_tools() { for f in $TOOLS; do chmod 750 "$f" 2>/dev/null || true; done; }
open_tools()  { for f in $TOOLS; do chmod 755 "$f" 2>/dev/null || true; done; }
trap open_tools EXIT
open_tools
echo "tools closed to the build user while the pay run runs: $(echo $TOOLS | tr '\n' ' ')"

# Build once, as the build user, with cgo off and no module downloads: the module has no
# dependencies and the box has no network.
setsid \
  setpriv --clear-groups --no-new-privs --reuid runner --regid runner \
  env HOME=/home/runner GOCACHE=/home/runner/gocache GOFLAGS=-mod=mod GOPROXY=off GOTOOLCHAIN=local CGO_ENABLED=0 \
  bash -c "cd $BUILD && go build -o $BUILD/payroll ." &
bpid=$!
wait "$bpid"
echo "build exit status: $?"
kill -TERM -- "-$bpid" 2>/dev/null || true
kill -KILL -- "-$bpid" 2>/dev/null || true
as_runner bash -c 'kill -9 -1' 2>/dev/null || true

# $1 = month directory, $2 = where this run's payroll.json is captured.
run_once() {
  local month="$1" out="$2" pid
  rm -rf /app/data /app/out
  mkdir -p /app/data /app/out
  cp -a "$month"/. /app/data/
  # Readable by the build user, writable by nobody: the root-only copies carry stricter modes.
  chmod -R u=rX,go=rX /app/data
  chown runner:runner /app/out
  close_tools
  # The binary is started directly, not through a shell, since the shells are closed too, and
  # from /app/payroll, the working directory the instruction's own command gives it, so a
  # program that resolves the data files relative to that directory finds them where it would
  # under that command.
  setsid \
    setpriv --clear-groups --no-new-privs --reuid runner --regid runner \
    env -C /app/payroll HOME=/home/runner "$BUILD/payroll" &
  pid=$!
  wait "$pid"
  echo "pay run exit status: $? ($month)"
  open_tools
  kill -TERM -- "-$pid" 2>/dev/null || true
  kill -KILL -- "-$pid" 2>/dev/null || true
  as_runner bash -c 'kill -9 -1' 2>/dev/null || true
  # Only a regular file is staged, and it is read with O_NOFOLLOW by the tests as well.
  rm -f "$out"
  if [ -L /app/out/payroll.json ] || [ ! -f /app/out/payroll.json ]; then
    echo "no regular /app/out/payroll.json after this run"
  else
    mv /app/out/payroll.json "$out"
    chown root:root "$out"
    chmod 600 "$out"
  fi
}

echo "=== the month that shipped ==="
run_once /opt/agent_data /opt/run_shipped.json
echo "=== a month the agent has never seen ==="
run_once /opt/holdout /opt/run_holdout.json

# Restore the agent's export exactly as collected.
rm -rf /app/data
mkdir -p /app/data
cp -a /opt/agent_data/. /app/data/
chmod -R u=rX,go=rX /app/data

as_runner bash -c 'kill -9 -1' 2>/dev/null || true

# -P keeps the working directory off sys.path, so agent code that wrote into /app cannot shadow
# the pytest module.
python -P -m pytest -o cache_dir=/tmp/pytest_cache \
  --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA
if [ "$?" -eq 0 ]; then echo 1 > /logs/verifier/reward.txt; else echo 0 > /logs/verifier/reward.txt; fi
exit 0
