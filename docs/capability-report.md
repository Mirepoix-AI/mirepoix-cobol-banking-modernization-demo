# Bounded capability and measurement report

The independent platform reviewer approved the bounded runtime integration on
2026-09-09. This report describes these reviewed snapshots, independently of the
documentation commit or future branch tips. Runtime evidence is pinned to demo
`faf9ea9dd1939d8fd1b5062d76bc77d21dbcc1eb` and platform
`7928a5f4ab81a5d2488aa06050c6f58899f854f5`. Both implementation PRs remain unmerged: [demo PR3](https://github.com/Mirepoix-AI/mirepoix-cobol-banking-modernization-demo/pull/3) and [platform PR76](https://github.com/Mirepoix-AI/mirepoix/pull/76).

## Capability and evidence

| Area | Implemented and exercised | Evidence boundary |
| --- | --- | --- |
| Numeric rule | Portable COBOL and Rust implementations; independent rational oracle; 201 deterministic inputs; five required arithmetic mutants detected | Local and hosted CI execution. Finite ASCII contract; not exhaustive arithmetic proof |
| Stateful batch | Separate COBOL/Rust transitions; complete balances, accepted IDs and journals; 126 invocations, including 48 before/after-commit restarts and two broken-recovery mutants | Local and CI. Synthetic three-account/12-record primary fixture; independent reviewer also exercised eight accounts/32 records |
| Evidence replay | Captured source, toolchain metadata, checksums, results and diagnostics; rebuild from bundle; CI artifact retained 30 days | Local replay of downloaded CI artifact. Checksums provide integrity, not independent attestation |
| Real Mirepoix validation | Captured platform `validate()` invoked on 201 arithmetic inputs and 12 full-state transitions through fixed, manifest-bound ELF roles | Local two-repository integration; standalone demo CI does not execute this optional integration |
| Failure handling | Known differences are divergent; malformed/tool failures stay unresolved; mixed divergence retains per-input unknown flags; timeout/interruption records absent raw verdict | Local real-validator adverse experiments, including exited-leader descendants and outer SIGTERM/SIGINT cleanup. Ordinary Linux process groups only |
| General modernization | No generated translation or native COBOL project ingestion exercised | No evidence of autonomous modernization, complete ME-2 orchestration, original mainframe runtime equivalence or production banking readiness |

## Timing and effort

One author capture at the final pair recorded **33.941 seconds** from harness start
to verified evaluation, immediately before outer evidence finalization. One subsequent
checkout-independent replay recorded **33.034 seconds** at the same boundary.
Outer checksum writing and archive compression follow that timestamp and are not
included in these elapsed values. This includes snapshot/build, the 201-case/five-mutant numeric
suite, the 126-invocation/48-restart stateful suite and all nine actual-validator
scenarios. These are one capture and one replay, not a latency bound or a benchmark average.
The reviewer independently checked its complete inventory and source identity and
reran the final validator scenarios; these timings remain author-measured.

Environment: Linux x86-64 on the implementation VM; GnuCOBOL 3.1.2, Rust 1.63.0,
GCC 12.2, Python 3.11.2, Bun 1.3.14 and captured Zod 3.25.76. Hardware utilization,
resource isolation and competing host work were not controlled.

The separate hosted [push CI run 34365475966](https://github.com/Mirepoix-AI/mirepoix-cobol-banking-modernization-demo/actions/runs/34365475966)
passed all 19 tests in **688.263 seconds**. That is the full adverse test-discovery
step, not one integration run. Its GnuCOBOL 3.1.2.0/Rust 1.98.1/GCC 13.3.0
artifact was independently downloaded, checksum verified and matched to all 35
captured demo inputs. [PR CI](https://github.com/Mirepoix-AI/mirepoix-cobol-banking-modernization-demo/actions/runs/34365482103)
also passed 19 tests in 801.895 seconds. The affected platform package passed
42 local tests, with one inherited Cargo-dependent test skipped because this local
toolchain lacks Cargo; [platform CI](https://github.com/Mirepoix-AI/mirepoix/actions/runs/34367358946) passed.

Operator active time, intervention count attributable to each run, generation trace
and model/VM costs were not measured. They remain unknown. There is no comparative
baseline, throughput guarantee, task-cost estimate or savings claim.

## Review and limitations

The independent runtime verdict is **APPROVE within the stated scope**. Earlier
findings included incomplete cleanup, misclassified outcomes, negative-experiment
false positives, replay layout refusal and malformed matching observations. Each
was corrected and independently rechecked; original reports and failed/unknown
evidence remain retained in the engineering review workspace. Independent review
is evidence for these snapshots, not certification of future commits.

Use the [standalone replay instructions](evidence-replay.md) and
[two-repository integration instructions](validator-integration.md) to reproduce
the respective workloads. Download the uniquely named artifact from the linked CI
run while its 30-day retention remains active. The local integration bundle also
contains platform source and its dependency; it is separate from the public demo
CI artifact and requires access to that platform source for an initial capture.
Known mismatches, failed runs and incomplete runs remain distinct; a nonzero child
exit alone does not establish mutation detection. The protocol adapter checks field
and bookkeeping validity; it does not replace the independent interest oracle.

No live model-serving workload, customer data, provisioning, merge or deployment
was part of this acceptance work. Native API cancellation remains synchronous;
the supplied external validator-worker supervisor owns process-group cleanup.
Deliberately escaped daemons, arbitrary filesystem races, hostile executable
sandboxing, exhaustive compiler coverage and physical power-loss recovery are
outside the tested contract.
