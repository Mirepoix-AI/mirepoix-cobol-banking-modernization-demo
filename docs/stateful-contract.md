# ME-25 synthetic account-interest batch: specification for independent review

Status: proposed before implementation. Public synthetic framing; no claim of
CardDemo file, transaction, CICS, VSAM or mainframe restart semantics.

## Inputs and state

A fixture contains up to eight named accounts with canonical signed decimal opening
balances, plus an ordered list of at most 32 interest records. Account IDs and record
IDs use ASCII letters/digits/hyphens; inputs include record ID, account ID and annual
rate. Numeric rules and errors are those of the reviewed numeric contract. Each
record applies monthly interest to the current account balance, then adds it to that
balance, checking both the interest and closing balance for S9(09)V99 representability.

Durable state contains the next record offset, every account balance, the complete
ordered journal and the accepted record-ID set. Journal rows record offset, record
ID, account, opening balance, computed interest, closing balance and disposition.
No random IDs, wall clocks or host-dependent values enter the expected state.

A repeated accepted record ID is a DUPLICATE with unchanged balances, even if its
payload differs: first accepted occurrence wins. Unknown account, malformed rate,
interest overflow and closing-balance overflow are REJECTED with unchanged balances.
Rejected rows advance the input offset and are journaled but do not reserve their
record IDs; a later valid retry of a rejected ID is permitted. Duplicate detection
precedes account/rate validation; otherwise unknown account precedes numeric errors.
All rows, including rejects and duplicates, are journaled exactly once per offset.

## Separate transition implementations

A COBOL program and a Rust program each read a persisted snapshot plus one record,
apply the transition and emit the complete proposed next state. Their transition
logic includes balance updates, duplicate/rejection handling and journal production.
The shared Python execution harness only frames files, launches programs, publishes
snapshots and injects failures; it does not compute the programs' next balances.
An independent Python exact-arithmetic state oracle computes the expected full state
from opening inputs and the record sequence, using the numeric specification rather
than calling either binary. Compare all balances, cursor, journal rows and accepted
IDs, including intermediate states, not only totals.

## Commit and restart contract

The harness writes each complete proposed state to a temporary file in the same
state directory, flushes/fsyncs it, then atomically replaces `checkpoint.json` and
fsyncs the directory. The replace is the declared visibility/commit boundary. The
single file includes balances, cursor, journal and IDs, avoiding a torn two-file
balance/journal commit. Platform prerequisites are local POSIX filesystems supporting
atomic same-directory rename and fsync. No multiwriter or network-filesystem contract.

Injected interruption BEFORE replacement discards the candidate; restart reads the
old cursor/state and repeats the record once. Interruption AFTER replacement reads
the new cursor/state and starts at the following record. A candidate file alone is
not a commit. Tests kill/stop the coordinator at those explicit hooks and start a
fresh process from disk. Normal results must equal the independent oracle; compare
actual on-disk state at interruption as well as final state after restart.

This is deterministic coordinator interruption, not physical power-loss certification.
Inputs are immutable and identified by hash in the checkpoint: restart against changed
opening accounts or record input must fail rather than reinterpret an old cursor.
Malformed checkpoint or inconsistent cursor/state must fail closed. No automatic
repair, concurrent writers or arbitrary corrupted-disk recovery is claimed.

## Acceptance cases and bounded fault model

Use multiple accounts, positive/negative/zero rates, repeated IDs, valid retry after
rejection, unknown accounts, malformed rates, interest overflow and closing overflow.
Exercise before/after replacement for every record in the small primary fixture.
Inject a broken restart coordinator that replays the last committed record without
honoring its accepted-ID state; complete balance/journal comparison must reject it.
A surviving broken restart mutant fails the suite.

Capture source/hash identity, opening inputs, records, every candidate/checkpoint,
interruption state, restart invocation, final balances/journal and mutant mismatch in
the ME-23 replay bundle. All local execution is bounded. The reviewer must approve
this specification before implementation; ME-23/24 remain prerequisite evidence.

## Revision 2: exact schema and recovery/publication rules

This section resolves ambiguities above and is normative where more specific.

Fixture JSON has `schemaVersion: 1`, ordered `accounts` entries `{id, balance}` and
ordered `records` entries `{id, account, rate}`. Account IDs are unique; IDs are
1–12 ASCII alphanumeric/hyphen characters. Rates are ASCII strings up to 64 bytes
without NUL/newline/tab (malformed numeric strings such as `abc` remain valid fixture
records). Opening balances are canonical, representable amounts. Fixture/schema
errors reject the whole invocation before any initial checkpoint is written.

A state object has exactly `schemaVersion`, `inputHash`, `next`, `balances`,
`acceptedIds`, `journal`. `inputHash` is SHA256 of canonical JSON (sorted object keys,
compact separators, ASCII encoding) of the complete validated fixture, including
account/record order. `balances` maps every opening account ID to a canonical amount;
`acceptedIds` lists IDs in first-acceptance order. `next` is an integer in [0,N].

Every journal row has exactly `offset`, `id`, `account`, `rate`, `disposition`,
`reason`, `opening`, `interest`, `closing`. Input identity fields equal the record
at `offset`; disposition is APPLIED, DUPLICATE or REJECTED. Fields below are literal
JSON null where specified, not empty strings or invented zeroes:

| Outcome (priority order) | reason | opening | interest | closing |
|---|---|---|---|---|
| Previously accepted ID | ACCEPTED_ID | null | null | null |
| Unknown account | UNKNOWN_ACCOUNT | null | null | null |
| Malformed rate | INVALID_INPUT | current balance | null | current balance |
| Rate field overflow | RATE_OVERFLOW | current balance | null | current balance |
| Computed interest overflow | INTEREST_OVERFLOW | current balance | null | current balance |
| Closing balance overflow | BALANCE_OVERFLOW | current balance | computed interest | current balance |
| Applied | null | current balance | computed interest | updated balance |

APPLIED alone changes balances and appends an accepted ID. DUPLICATE uses null
amounts even when its new payload names an unknown account; duplicate detection
precedes payload validation. Rejections and duplicates advance `next` and append
one journal row. Add explicit cases for each row of this table and duplicate-ID
with unknown-account payload. Rejected IDs can be retried by a later valid record.

### Checkpoint ownership and validation

The coordinator owns fixture/checkpoint validation and publication. On every load,
require exact keys/types/version, matching fixture hash, cursor bounds, exact account
set, canonical representable balances, journal length equal to cursor, contiguous
offsets 0..next-1, exact journal input identity, known disposition/reason/nullability,
and unique acceptedIds matching APPLIED rows in order. Reconstruct the balance chain
from opening balances and journal: each referenced opening equals the preceding
balance, only APPLIED changes it, and final balances equal this chain; accepted IDs
cannot appear twice as APPLIED and duplicate/rejected semantics must agree with prior
accepted IDs/account existence. A malformed or inconsistent state fails closed.
These structural/bookkeeping checks do not substitute for the independently computed
numeric expected-state oracle used in acceptance tests.

Initialization is an explicit mode: it refuses an existing checkpoint and durably
publishes opening state (next=0, empty journal/IDs). Restart is a separate mode:
missing checkpoint is an error, never silent reinitialization. After initialization
and after each commit, the same validation applies. Stray candidate files left from
an interrupted run are ignored and removed only after the authoritative checkpoint
is successfully loaded. Existing valid checkpoint plus absent candidate is normal.
If an initial publication fails, operator inspection is required; a missing checkpoint
can be initialized only through the explicit initialization mode.

### Successful execution before commit

Domain rejects are successful transition executions: exit 0, empty stderr and a
complete valid candidate state with the specified REJECTED journal row. A nonzero
exit, signal, missing executable/compiler, timeout, nonempty stderr, malformed or
truncated output, or failed candidate validation is an infrastructure/protocol failure.
It leaves the previous checkpoint authoritative and stops the batch; it is never
journaled as a domain rejection or accepted as a successful record.

Candidate validation also requires next=old.next+1, an unchanged journal prefix plus
exactly one new row, unchanged inputHash/version/account set, and all bookkeeping
checks above. Programs receive the old state and one immutable record and may not
silently drop previous entries. Execution is bounded to 3 seconds per transition
plus a 1-second cleanup grace. The coordinator supervises ordinary Linux process
groups, escalates TERM to KILL and requires confirmed group exit and drained output
before publication. Uncertain cleanup stops the run without publication. Deliberate
setsid/daemon escape is outside this trusted local workload contract.

Write/fsync/rename/directory-fsync failure stops execution as incomplete; do not
retry blindly. Before rename, the old checkpoint remains authoritative. Once rename
succeeds, the new state may already be authoritative even if directory fsync fails;
record that uncertainty and require explicit restart/inspection against what is on
disk. The AFTER hook fires only after rename and directory fsync succeed. A fresh
restart validates on-disk checkpoint identity/consistency before doing any work.

Acceptance additionally injects: missing/malformed/inconsistent checkpoint; changed
fixture; transition nonzero exit, timeout, truncated output and unexpected stderr;
pre-rename write failure; and a post-rename directory-fsync failure where readable
new state may persist but the failed invocation must not claim success. Preserve
raw process result, publication phase and observed disk state for these faults.

Numeric reference: `docs/numeric-contract.md` at demo commit
`7acaa66863d025234ca6dff464e10ef80e2ed6cb`, subject to ME-24 independent acceptance.
Canonical amounts follow that contract (no leading plus or redundant zeroes; negative
zero is `0.00`). JSON object key order is irrelevant; journal/accepted-ID order is
significant. Wire formats may differ, but decoded logical state must match exactly.

Concrete journal examples (offset/input fields shown for each scenario):

```json
{"offset":0,"id":"r1","account":"A","rate":"12.00","disposition":"APPLIED","reason":null,"opening":"100.00","interest":"1.00","closing":"101.00"}
{"offset":1,"id":"r1","account":"UNKNOWN","rate":"abc","disposition":"DUPLICATE","reason":"ACCEPTED_ID","opening":null,"interest":null,"closing":null}
{"offset":2,"id":"r2","account":"UNKNOWN","rate":"abc","disposition":"REJECTED","reason":"UNKNOWN_ACCOUNT","opening":null,"interest":null,"closing":null}
{"offset":3,"id":"r2","account":"A","rate":"abc","disposition":"REJECTED","reason":"INVALID_INPUT","opening":"101.00","interest":null,"closing":"101.00"}
{"offset":4,"id":"r2","account":"A","rate":"0.00","disposition":"APPLIED","reason":null,"opening":"101.00","interest":"0.00","closing":"101.00"}
```

With separate account B at 999999999.99: rate 9999.99 rejects INTEREST_OVERFLOW
with opening=closing=999999999.99 and interest=null. Rate 12.00 rejects
BALANCE_OVERFLOW with opening=closing=999999999.99 and interest=9999999.99.
