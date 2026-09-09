# Synthetic batch implementation and evidence

`docs/stateful-contract.md` preserves the approved revision 2 specification unchanged
(SHA256 `2d5a75384241e488ca8de190655658dfda932750fdec31ada039e299708ea1d0`).
The implementation is submitted for separate runtime review.

`src/stateful.cob` and `src/stateful.rs` independently implement transitions over
up to eight accounts and 32 records. The coordinator validates immutable input and
checkpoint bookkeeping, frames stdin/stdout, and publishes each complete state.
Python's exact rational oracle supplies acceptance expectations; it never supplies
a candidate in place of either program. The wire protocol is line-oriented with
hex-encoded rate bytes, so invalid rates containing delimiters remain unambiguous.
Only coordinator-validated inputs belong to this private wire contract.

The primary fixture contains three accounts and 12 records. Full comparisons cover
normal and intermediate state, 48 before/after interruption points across the two
implementations, fresh-process restart, two broken recovery mutants, invalid or
missing checkpoints, changed input identity, write and directory-sync failures,
and nonzero, diagnostic, truncated and timed-out transition processes.

The BEFORE hook exits the coordinator after candidate-file fsync, immediately
before replacement. The AFTER hook exits only after replacement and directory fsync.
`last-attempt.json` records raw process output, errors and publication phase.
`interrupted-state.json` captures the authoritative on-disk state before recovery;
`committed-N.json` and `candidate-N.json` retain full observations. The checksum
inventory and portable replay bundle include these files, expected states, binaries,
all invocation arguments/results and captured source.

Run `./run.sh --output /tmp/stateful-evidence` and inspect `evaluation.json`'s
`stateful` field and the `stateful/` directory. Replay and CI retain the numeric
suite and all five arithmetic mutations too. `python3 -B -m unittest discover -s
tests -v` additionally tests outer SIGTERM/SIGINT with a surviving nested transition
child and requires an incomplete bundle with an unchanged checkpoint.

The process contract covers cooperative cancellation and ordinary Linux process
groups. Nested supervisors allow time for their children to be reaped before
escalation. Deliberately escaped daemons, power-loss durability, concurrent writers,
network filesystems, banking transaction semantics and whole-system equivalence
remain outside this experiment. This tranche does not invoke Mirepoix's validator;
that is the separately gated ME-26 integration.

A witnessed full-state mismatch, changed checkpoint, or surviving required recovery
mutant is `failed`, with case/invocation and expected/actual evidence in
`stateful/failing-cases.json`. Execution, storage, or protocol uncertainty remains
`incomplete`. Negative tests inject a +1-cent stateful transition and a surviving
recovery mutant; the behavioral mismatch bundle must replay as `failed`.

Negative acceptance requires evidence of the intended cause, not merely a nonzero
exit. Each fresh coordinator invocation writes `outcome.json`; the suite retains
it with the raw invocation before another run can overwrite it. Recovery detection
requires the actual before/after mutation, independently expected mutated candidate,
clean transition completion, and the expected balance-chain validation rejection.
Checkpoint, publication and process fault tests likewise match their exact phase,
error and (where applicable) process observation. An unrelated failure makes the
experiment incomplete. Regression fixtures inject unrelated I/O failures into all
four negative-test families, including an incomplete recovery-experiment replay.
