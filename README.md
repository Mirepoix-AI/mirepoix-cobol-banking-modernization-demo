# Mirepoix COBOL banking modernization demo

> **Bounded public demonstration—not a production modernization capability,
> proprietary banking-platform implementation, or validator integration.**

This repository demonstrates one auditable claim:

> For the pinned Apache-2.0 AWS CardDemo monthly-interest rule and the committed
> fixture set, a portable GnuCOBOL oracle and a dependency-free Rust
> implementation produce the same canonical outputs.

The harness also compiles a deliberately incorrect Rust variant and requires the
comparison to report `DIVERGENT`. This proves that the demonstration can detect a
controlled semantic mutation instead of merely producing a green result.

## Why this example exists

Core-banking modernization cannot be demonstrated responsibly with proprietary
customer or platform source. This example uses one small rule from AWS's public,
Apache-2.0-licensed CardDemo repository and makes a reproducible claim about that
rule.

The workflow illustrates a safer modernization pattern:

1. isolate a bounded legacy behavior;
2. retain the legacy implementation as an executable oracle;
3. implement the behavior in a target language;
4. exercise decimal, error, and representability boundaries;
5. inject a known defect to test the comparison; and
6. package the results and toolchain metadata as verifiable evidence.

It does not claim compatibility with any proprietary core-banking product. A real
engagement requires appropriately licensed customer code, customer and platform
subject-matter expertise, system metadata, and customer-owned acceptance tests.

## Run locally

Prerequisites: Bash, GnuCOBOL (`cobc`), Rust (`rustc`), Python 3, `tar`, and a
SHA-256 utility.

Run the baseline and mutation demonstration:

```sh
./run.sh
```

Retain the evidence at an explicit, empty directory:

```sh
./run.sh --output /tmp/carddemo-interest-evidence
```

Expected terminal verdicts:

```text
EQUIVALENT baseline ...
DIVERGENT controlled-mutation ...
```

The GitHub Actions workflow in `.github/workflows/equivalence.yml` runs the same
check for every push and pull request.

`result.json` is the machine-readable verdict. `SHA256SUMS` covers inputs,
compiler versions, binaries, execution tables, and the result. The adjacent
`.tar.gz` is the portable evidence bundle. Generated evidence and binaries belong
outside this source directory and must not be committed.

`--mutation` selects mutation-focused terminal output. The evidence still evaluates
the baseline, and the command exits zero only when the baseline is `EQUIVALENT` and
the machine-readable mutation verdict is `DIVERGENT`.

## Semantics

Inputs are strict signed fixed decimals:

- balance: `S9(09)V99` (up to nine integral digits and exactly two fractional digits);
- annual interest rate: `S9(04)V99` (up to four integral digits and exactly two fractional digits);
- monthly result: `S9(09)V99`.

The GnuCOBOL adapter compiles the pinned expression without `ROUNDED`. Rust parses
values into checked scaled integers, uses no binary floating point or third-party
crates, performs checked multiplication, and relies on signed integer division's
truncation toward zero. Both emit:

- success: `OK<TAB>canonical-decimal`, exit 0;
- malformed input: `ERROR<TAB>INVALID_INPUT`, exit 2;
- field/result overflow: `ERROR<TAB>OVERFLOW`, exit 3.

Result overflow is evaluated on the *truncated* monthly result—the value stored in
`S9(09)V99`—rather than on the untruncated quotient. A product whose exact quotient
exceeds `999999999.99` but truncates toward zero to a representable value is
reported `OK`; both implementations agree on this boundary in fixtures
`truncated-fit-positive` and `truncated-fit-negative`.

Fixtures cover zero, positive and negative signs, representable boundaries,
fractional-cent truncation, argument framing, mixed error precedence, strict
malformed values, input field overflow, and result overflow.

## Provenance, licensing, and limitations

See [`PROVENANCE.md`](PROVENANCE.md), [`upstream/LICENSE`](upstream/LICENSE), and
[`upstream/NOTICE`](upstream/NOTICE). The source rule is pinned to CardDemo commit
`59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e`.

Mirepoix-authored material is available under the Business Source License 1.1 in
[`LICENSE`](LICENSE). The identified AWS-derived material remains under Apache-2.0.
Commercial licensing is available from `licensing@mirepoix-ai.com`.

A green result proves only the extracted monthly-interest rule for the committed
fixture set. It does **not** prove full CardDemo, IBM z/OS, CICS, VSAM, JCL,
assembler, or whole-system equivalence. It does not advertise native production
COBOL modernization support.
