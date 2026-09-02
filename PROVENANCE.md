# CardDemo source provenance

This throwaway prototype is derived only from the public Apache-2.0 repository:

- Repository: <https://github.com/aws-samples/aws-mainframe-modernization-carddemo>
- Commit: `59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e`
- License: Apache-2.0; see [`upstream/LICENSE`](upstream/LICENSE)
- Notice: see [`upstream/NOTICE`](upstream/NOTICE)

The portable COBOL oracle preserves these bounded elements from that commit:

| Upstream path | Lines | Element |
|---|---:|---|
| `app/cbl/CBACT04C.cbl` | 1–20 | program identity, purpose, and Apache notice |
| `app/cbl/CBACT04C.cbl` | 168–169 | `WS-MONTHLY-INT PIC S9(09)V99` |
| `app/cbl/CBACT04C.cbl` | 462–470 | monthly-interest `COMPUTE` expression |
| `app/cpy/CVTRA01Y.cpy` | 4–10 | `TRAN-CAT-BAL PIC S9(09)V99` |
| `app/cpy/CVTRA02Y.cpy` | 4–10 | `DIS-INT-RATE PIC S9(04)V99` |

The extracted rule is:

```cobol
COMPUTE WS-MONTHLY-INT
    = (TRAN-CAT-BAL * DIS-INT-RATE) / 1200
```

No `ROUNDED` phrase is present. The adapter makes the resulting truncation to two fractional decimal places explicit and adds portable input/output/error framing solely for deterministic comparison.

This prototype does not copy, execute, or claim equivalence for CardDemo's CICS, VSAM, JCL, Db2, IMS, MQ, assembler, full batch flow, or whole application.
