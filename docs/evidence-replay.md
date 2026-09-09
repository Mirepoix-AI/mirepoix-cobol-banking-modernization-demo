# Captured evidence and replay

`./run.sh --output /tmp/interest-run` captures the harness, sources, tests, complete
fixture configuration, docs, provenance, licenses and workflow into `inputs/` before
compilation. Compilers read only those captured sources. Git commit and dirty status
are recorded separately: a dirty run describes a working snapshot based on that
commit and does not claim byte identity with it. Input hashes identify actual bytes.
Use a clean commit for review/CI acceptance. The invocation, full compile commands,
compiler versions, Python/OS versions and selected build settings are recorded.

The result states are `verified` (all baseline/oracle comparisons pass and every
required mutant is killed), `failed` (behavior/fixture mismatch or surviving mutant),
and `incomplete` (e.g. unavailable/failed compiler or harness failure). Both nonverified
states exit nonzero. Each case compares stdout, stderr and exit status. Diagnostics,
full observations, generated corpus, failed cases and mutant-killing IDs are retained.
Runs are bounded to 201 cases, 90 seconds per compilation, 3 seconds per case invocation
and 300 seconds for the evaluator; CI has a 10-minute outer limit. Abrupt host loss or
SIGKILL can prevent finalization; absent/partial evidence never establishes success.

`SHA256SUMS` covers every bundle file except itself, including binaries, outputs,
result manifest and replay harness. The adjacent tar.gz is the artifact uploaded by
CI on success or failure whenever it exists. Artifact names contain GitHub's tested
SHA, run ID and attempt; PR runs may use GitHub's synthetic merge SHA, which is also
recorded as the actual checked-out demo commit. Retention is 30 days. Missing artifacts
from setup/host failure are not a successful result. Retain/download evidence before
expiry if it is needed for an acceptance record.

## Replay without the source checkout

Download the artifact from the GitHub Actions run and unpack its tar.gz in a fresh
directory. Only replay bundles whose source you trust: they contain executable code.

```sh
mkdir -p /tmp/interest-replay-input
# Replace the filename with the downloaded artifact's tar.gz.
tar -xzf carddemo-evidence.tar.gz -C /tmp/interest-replay-input
python3 /tmp/interest-replay-input/carddemo-evidence/replay.py \
  --output /tmp/interest-replayed
```

Replay verifies the exact file inventory and every checksum before invoking the
captured evaluator. Tampered inputs or extra/missing files are refused. It recompiles
from `inputs/`, writes a fresh evidence bundle, preserves original demo identity and
records the parent checksum-manifest hash. No original Git checkout is needed.
Compiler paths and commands in the *new* bundle describe the replay environment;
byte-identical executables or timing across machines are not promised.

Prerequisites: Linux/POSIX, Python 3.10+, Bash, GnuCOBOL 3.1+, Rust 1.63+, GCC/linker
and their runtime/development libraries. CI uses Ubuntu 24.04; initial local execution
used Debian 12 with GnuCOBOL 3.1.2 and Rust 1.63.0. No Python/Rust third-party libraries
are used. Local compiler search paths can be configured normally but are not carried
as executable configuration into another host. Toolchain compatibility is checked by
recompilation and behavior, not assumed from a filename.

Checksums establish internal integrity against the supplied manifest. They are not
a signature, independent attestation, or protection against someone rewriting both
evidence and hashes. A replayed green result does not independently validate this
oracle's correctness or expand the demo's capability claim.

## Validation

`python3 -B -m unittest discover -s tests -v` runs real compiler fixtures for successful
copy/replay, a deliberately wrong committed expectation with retained failed replay,
compiler failure with diagnostics, input tampering refused before execution, and a
required surviving mutant that must fail. Numeric tests check hand derivations and
reproducibility. Historical defect fixtures should never be interpreted as production
coverage. The independent reviewer owns acceptance of these checks.
