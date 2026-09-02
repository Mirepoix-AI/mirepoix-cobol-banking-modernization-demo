#!/usr/bin/env bash
# Reproducible harness for the bounded CardDemo monthly-interest equivalence claim.
set -euo pipefail

SCRIPT_DIR=$(cd -P -- "$(dirname -- "$0")" && pwd)
readonly SCRIPT_DIR
readonly FIXTURES="$SCRIPT_DIR/fixtures/cases.tsv"
readonly CLAIM="For the pinned CardDemo monthly-interest rule and committed fixture set, the portable GnuCOBOL oracle and dependency-free Rust implementation produce the same canonical outputs."
readonly UPSTREAM_COMMIT="59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e"
MODE=all
OUTPUT=""

usage() {
  cat <<'USAGE'
Usage: ./run.sh [--output DIRECTORY] [--mutation]

Without flags, builds both implementations, proves the baseline EQUIVALENT,
and proves the controlled Rust mutation DIVERGENT. --mutation runs only the
controlled mutation demonstration. Generated binaries and evidence are written
outside the source tree unless --output is supplied.
USAGE
}

while (($# > 0)); do
  case "$1" in
    --output)
      [[ $# -ge 2 ]] || { echo "ERROR: --output requires a directory" >&2; exit 64; }
      OUTPUT=$2
      shift 2
      ;;
    --mutation)
      MODE=mutation
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage >&2
      exit 64
      ;;
  esac
done

for command in cobc rustc python3 tar; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "ERROR: required command not found: $command" >&2
    exit 69
  }
done

if [[ -z "$OUTPUT" ]]; then
  OUTPUT=$(mktemp -d "${TMPDIR:-/tmp}/carddemo-interest-evidence.XXXXXX")
else
  mkdir -p "$OUTPUT"
  if find "$OUTPUT" -mindepth 1 -maxdepth 1 -print -quit | grep -q .; then
    echo "ERROR: output directory must be empty: $OUTPUT" >&2
    exit 73
  fi
fi
OUTPUT=$(cd -P -- "$OUTPUT" && pwd)
readonly OUTPUT
readonly BUILD="$OUTPUT/build"
readonly EXECUTION="$OUTPUT/execution"
readonly INPUTS="$OUTPUT/inputs"
mkdir -p "$BUILD" "$EXECUTION" "$INPUTS"

cp "$SCRIPT_DIR/src/carddemo-interest.cob" "$INPUTS/"
cp "$SCRIPT_DIR/src/carddemo-interest.rs" "$INPUTS/"
cp "$FIXTURES" "$INPUTS/"
cp "$SCRIPT_DIR/PROVENANCE.md" "$INPUTS/"
cp "$SCRIPT_DIR/upstream/LICENSE" "$INPUTS/LICENSE.carddemo-apache-2.0"
cp "$SCRIPT_DIR/upstream/NOTICE" "$INPUTS/NOTICE.carddemo"

(
  cd "$SCRIPT_DIR"
  cobc -x -free -Wall -o "$BUILD/carddemo-interest-cobol" src/carddemo-interest.cob
) >"$BUILD/cobol-build.log" 2>&1
(
  cd "$SCRIPT_DIR"
  rustc --edition=2021 -D warnings -C overflow-checks=yes \
    -o "$BUILD/carddemo-interest-rust" src/carddemo-interest.rs
  rustc --edition=2021 -D warnings -C overflow-checks=yes \
    --cfg carddemo_mutation \
    -o "$BUILD/carddemo-interest-rust-mutant" src/carddemo-interest.rs
) >"$BUILD/rust-build.log" 2>&1
cobc -V >"$BUILD/cobc-version.txt"
rustc -Vv >"$BUILD/rustc-version.txt"

printf 'caseId\tcategory\texpectedExit\toracleExit\trustExit\texpectedOutput\toracleOutput\trustOutput\tverdict\n' \
  >"$EXECUTION/baseline.tsv"
printf 'caseId\tcategory\toracleExit\tmutantExit\toracleOutput\tmutantOutput\tverdict\n' \
  >"$EXECUTION/mutation.tsv"

case_count=0
baseline_failed=0
mutation_differences=0
valid_case_count=0

run_case() {
  local binary=$1 balance=$2 rate=$3 stdout_file=$4 stderr_file=$5
  local status
  set +e
  "$binary" "$balance" "$rate" >"$stdout_file" 2>"$stderr_file"
  status=$?
  set -e
  printf '%s' "$status"
}

while IFS=$'\t' read -r case_id category balance rate expected_exit expected_tag expected_value; do
  [[ -n "$case_id" && "${case_id:0:1}" != "#" ]] || continue
  case_count=$((case_count + 1))
  [[ "$expected_exit" == "0" ]] && valid_case_count=$((valid_case_count + 1))
  expected_output="${expected_tag}"$'\t'"${expected_value}"

  oracle_stdout="$EXECUTION/.oracle-${case_id}.out"
  oracle_stderr="$EXECUTION/.oracle-${case_id}.err"
  rust_stdout="$EXECUTION/.rust-${case_id}.out"
  rust_stderr="$EXECUTION/.rust-${case_id}.err"
  mutant_stdout="$EXECUTION/.mutant-${case_id}.out"
  mutant_stderr="$EXECUTION/.mutant-${case_id}.err"

  oracle_exit=$(run_case "$BUILD/carddemo-interest-cobol" "$balance" "$rate" "$oracle_stdout" "$oracle_stderr")
  rust_exit=$(run_case "$BUILD/carddemo-interest-rust" "$balance" "$rate" "$rust_stdout" "$rust_stderr")
  mutant_exit=$(run_case "$BUILD/carddemo-interest-rust-mutant" "$balance" "$rate" "$mutant_stdout" "$mutant_stderr")
  oracle_output=$(cat "$oracle_stdout")
  rust_output=$(cat "$rust_stdout")
  mutant_output=$(cat "$mutant_stdout")

  baseline_verdict=PASS
  if [[ "$oracle_exit" != "$expected_exit" || "$rust_exit" != "$expected_exit" \
     || "$oracle_output" != "$expected_output" || "$rust_output" != "$expected_output" \
     || -s "$oracle_stderr" || -s "$rust_stderr" ]]; then
    baseline_verdict=FAIL
    baseline_failed=$((baseline_failed + 1))
  fi

  mutation_verdict=SAME
  if [[ "$mutant_exit" != "$oracle_exit" || "$mutant_output" != "$oracle_output" ]]; then
    mutation_verdict=DIFFERENT
    mutation_differences=$((mutation_differences + 1))
  fi
  if [[ -s "$mutant_stderr" ]]; then
    echo "ERROR: mutant wrote stderr for case $case_id" >&2
    exit 1
  fi

  printf '%s\t%s\t%s\t%s\t%s\t%q\t%q\t%q\t%s\n' \
    "$case_id" "$category" "$expected_exit" "$oracle_exit" "$rust_exit" \
    "$expected_output" "$oracle_output" "$rust_output" "$baseline_verdict" \
    >>"$EXECUTION/baseline.tsv"
  printf '%s\t%s\t%s\t%s\t%q\t%q\t%s\n' \
    "$case_id" "$category" "$oracle_exit" "$mutant_exit" \
    "$oracle_output" "$mutant_output" "$mutation_verdict" \
    >>"$EXECUTION/mutation.tsv"

  rm -f "$oracle_stdout" "$oracle_stderr" "$rust_stdout" "$rust_stderr" \
    "$mutant_stdout" "$mutant_stderr"
done <"$FIXTURES"

baseline_verdict=DIVERGENT
[[ "$baseline_failed" -eq 0 ]] && baseline_verdict=EQUIVALENT
mutation_verdict=NOT_DETECTED
[[ "$mutation_differences" -eq "$valid_case_count" && "$valid_case_count" -gt 0 ]] \
  && mutation_verdict=DIVERGENT

env BASELINE_VERDICT="$baseline_verdict" \
  MUTATION_VERDICT="$mutation_verdict" \
  CLAIM="$CLAIM" \
  UPSTREAM_COMMIT="$UPSTREAM_COMMIT" \
  CASE_COUNT="$case_count" \
  BASELINE_FAILED="$baseline_failed" \
  MUTATION_DIFFERENCES="$mutation_differences" \
  VALID_CASE_COUNT="$valid_case_count" \
  MODE="$MODE" \
  python3 - <<'PY' >"$OUTPUT/result.json"
import json
import os

baseline = os.environ["BASELINE_VERDICT"]
mutation = os.environ["MUTATION_VERDICT"]
mode = os.environ["MODE"]
overall = "PASS" if mutation == "DIVERGENT" and (mode == "mutation" or baseline == "EQUIVALENT") else "FAIL"
print(json.dumps({
    "schemaVersion": 1,
    "claim": os.environ["CLAIM"],
    "upstream": {
        "repository": "https://github.com/aws-samples/aws-mainframe-modernization-carddemo",
        "commit": os.environ["UPSTREAM_COMMIT"],
        "license": "Apache-2.0",
    },
    "mode": mode,
    "baseline": {
        "verdict": baseline,
        "cases": int(os.environ["CASE_COUNT"]),
        "failedCases": int(os.environ["BASELINE_FAILED"]),
    },
    "mutation": {
        "verdict": mutation,
        "validCases": int(os.environ["VALID_CASE_COUNT"]),
        "differingCases": int(os.environ["MUTATION_DIFFERENCES"]),
    },
    "overall": overall,
}, indent=2, sort_keys=True))
PY

(
  cd "$OUTPUT"
  if command -v sha256sum >/dev/null 2>&1; then
    find build execution inputs -type f -print | LC_ALL=C sort | xargs sha256sum
    sha256sum result.json
  else
    find build execution inputs -type f -print | LC_ALL=C sort | xargs shasum -a 256
    shasum -a 256 result.json
  fi
) >"$OUTPUT/SHA256SUMS"

bundle="${OUTPUT%/}.tar.gz"
tar -czf "$bundle" -C "$(dirname "$OUTPUT")" "$(basename "$OUTPUT")"

if [[ "$MODE" != "mutation" ]]; then
  echo "$baseline_verdict baseline cases=$case_count failed=$baseline_failed"
fi
echo "$mutation_verdict controlled-mutation validCases=$valid_case_count differingCases=$mutation_differences"
echo "evidence=$OUTPUT"
echo "bundle=$bundle"

if [[ "$mutation_verdict" != "DIVERGENT" ]]; then
  exit 1
fi
if [[ "$MODE" != "mutation" && "$baseline_verdict" != "EQUIVALENT" ]]; then
  exit 1
fi
