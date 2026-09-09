# ME-26: real Mirepoix validation, locally captured and supervised

This integration invokes the actual `validate()` public entry point from a captured
`packages/validate/src/index.ts` at the recorded platform Git identity. It uses the
ADR-018 fixed `mirepoix-cobol-demo-v1` execution path. The copied source and zod
runtime dependency are included in the local checksum inventory; no substitute
validator or fabricated aggregate is used. The ordinary demo CI exercises its own
harness and supervisor tests; this two-repository integration is a separate local
acceptance run.

## Run and replay

Prerequisites: Linux with `/proc`, local POSIX storage, Python 3, GnuCOBOL, Rust,
GCC/cc, Bun, and a platform checkout containing the reviewed adapter and its installed
zod dependency. No model service, network provisioning or customer data is used.

```sh
python3 -B tools/validator_evidence.py --platform /path/to/mirepoix \
  --bun /path/to/bun --output /tmp/validator-evidence
python3 /tmp/validator-evidence/replay.py --bun /path/to/bun \
  --output /tmp/validator-replayed
```

Replay requires only the unpacked **trusted** bundle and the declared toolchains;
it does not require either original checkout. It checks the complete inventory
before executing captured source. The original demo/platform Git identity and dirty
state remain explicit. Dirty development runs are recorded as such; final review
requires clean, exact source identities. Integration bundles include platform and
third-party source locally; they are not uploaded by the standalone demo CI.

## What executes

The base numeric and stateful/restart harness first compiles captured sources and
retains its full oracle evidence. Then independent Bun worker invocations call the
real validator on all 201 arithmetic inputs and the 12 full-state transitions of
the primary fixture. Stateful inputs contain each specified prefix state and next
record; the validator compares the complete returned wire representation. Durable
checkpoint/restart behavior remains separately evidenced by the base ME-25 suite.

Separate invocations demonstrate arithmetic and stateful divergence, matching tool
failures that remain INDETERMINATE, and a mixed mismatch/tool failure whose aggregate
is DIVERGENT while its failing input remains explicitly unresolved. The fault fixture
is compiled from captured C; all substituted roles and their parent manifest are
recorded. Negative acceptance requires the intended tool diagnostic, not just an
unknown aggregate. Unexpected uncertainty makes the integration incomplete; a
witnessed wrong verdict fails it.

## Cancellation and outcomes

The synchronous platform API has no native AbortSignal contract. The actual Bun
worker and its workload descendants share an external supervisor's process group.
The supervisor confirms ordinary group cleanup even after the worker leader exits;
it escalates TERM to KILL within a one-second cleanup bound. Explicit timeout and
ready-child cancellation cases exercise a TERM-ignoring descendant. A worker killed
before `validate()` returns has `rawVerdict: null`, with a separate timed-out or
interrupted supervisory outcome. It never acquires an invented INDETERMINATE return.

Per-invocation `request.json`, stdout/stderr, `supervision.json` and `result.json`
retain raw API verdicts and every per-input unknown flag. Worker start/end timestamps
bound the actual validate call; supervisory timestamps include startup and cleanup.
Overall elapsed time also includes capture, compilation and adverse checks. Operator
active minutes/interventions and model cost/generation data are unavailable, recorded
as null with reasons. No savings or generated-translation claim follows from these
measurements.

Ordinary Linux groups are a trusted local-workload contract: deliberate setsid escape,
hostile executables, remote inference stop, production confinement and power-loss
certification are not exercised. The fixed adapter hashes selected ELF bytes and
executes a private copy; checksums do not authenticate the operator or dynamic host
libraries. Native COBOL project ingestion, translation generation and end-to-end
modernization orchestration remain separate ME-2 work.

Run the explicit acceptance checks against a completed local bundle:

```sh
python3 -B tools/check_validator_evidence.py --bundle /tmp/validator-evidence \
  --bun /path/to/bun --output /tmp/validator-checks
```

These checks replay from captured source, refuse a tampered platform snapshot before
execution, and send SIGTERM/SIGINT to the outer harness while its actual Bun validator
has a live TERM-ignoring child. They require incomplete evidence, a null raw verdict,
and confirmed disappearance of the child, worker and driver. They are separate from
the default single-repository CI tests because they require the completed local
integration bundle and declared Bun/compiler environment.
