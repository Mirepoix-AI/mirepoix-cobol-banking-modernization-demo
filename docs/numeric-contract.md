# Numeric contract and independent oracle

The pinned AWS expression is `(balance * annual_rate) / 1200`, assigned without
ROUNDED to S9(09)V99. Everything below about CLI framing and errors is a portable
adapter contract, not a claim about CardDemo's original input/runtime behavior.

## Domain and framing

The test domain is ASCII command-line arguments without NUL (OS argv cannot carry
NUL). Exactly two arguments are required. Each is captured at its first 64 bytes,
then surrounding ASCII spaces are removed. One optional leading sign is permitted.
Balance has 1–9 integral digits and exactly two fractional digits; rate has 1–4
integral digits and exactly two fractional digits. Leading zeros count toward field
width. Unicode and arbitrary non-UTF-8 process bytes are outside this declared domain.

Validation order is part of the adapter: wrong argument count is INVALID_INPUT.
For each field, fewer than four unsigned characters is invalid; otherwise more
than the allowed integral width (unsigned length minus three) is OVERFLOW even
when those characters are malformed. Remaining fields require ASCII digits and
the decimal point at the two-fractional-digit position. Both fields are classified;
any OVERFLOW outranks INVALID_INPUT from the other field. This ordering is tested.

## Arithmetic and observable result

Compute the exact mathematical amount, truncate toward zero to cents, then test
representability against [-999999999.99, 999999999.99]. Range checks on the raw
fraction would incorrectly reject a quotient that truncates into range. Both signs
of zero render as `0.00`. Success prints `OK<TAB>amount<LF>` and exits 0. Invalid
input prints `ERROR<TAB>INVALID_INPUT<LF>` and exits 2; overflow prints
`ERROR<TAB>OVERFLOW<LF>` and exits 3. Stderr must be empty. Observations compare the
full stdout, stderr and exit status, including newline characters.

## Oracle reasoning (author rationale for independent review)

`tools/numeric.py` parses values as Python Fraction quantities in their original
currency/rate units. It computes rational monthly interest and applies Python's
Fraction-to-int truncation only after multiplying the amount by 100. It does not
import either implementation, reuse their fixed-point parser or invoke either
binary to obtain expected values. Adapter classification is necessarily an explicit
implementation of the common framing contract; it is not claimed to be independent
of the specified policy. The mathematical representation differs from Rust's scaled
i128 algorithm and COBOL's decimal fields. An independent reviewer must assess this
reasoning; author-written oracle tests alone are not reviewer acceptance.

Hand-derived checks: 100.00 at 12.00 yields 1.00; 6.00 at 1.00 yields exactly half
a cent, truncating to 0.00 for either sign; 12.00 at 1.00 yields one cent. The
999991666.73 at 1200.01 case has an exact amount greater than 999999999.99 but less
than 1000000000.00, so truncation is representable. These examples are independently
asserted in `tests/test_numeric.py` as well as checked against committed fixtures.

## Coverage and limits

The bounded corpus has 25 original hand fixtures, 16 explicit boundary/framing
cases and 160 generated cases using seed 20260909 (201 total). Python's seeded
`random.Random` and its recorded Python version define generation; the full generated
corpus is retained in each evidence bundle. Tested cases and all observations remain
available even on mismatch. This finite corpus is not proof over the full domain.

Five Rust compile-time mutants are evaluated: one-cent shift, nearest/away-from-zero
rounding at a tie, lost negative sign, annual rather than monthly divisor, and missing
result-range check. `mutations.json` records the case IDs that kill each; no required
mutant may survive. A mutant kill compares it to the independent oracle, not merely
to another possibly wrong implementation. Baseline mismatches separately fail the run.
Equivalent/inapplicable mutants would need explicit explanation and a revised agreed
contract; none of these five is considered equivalent or waived.
