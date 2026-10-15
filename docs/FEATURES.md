# UNTANGLE feature checklist

Status values: **Not started**, **In progress**, **Implemented**, **Tested**.

Upload and the PDF type verdict are tested. The landing page, dashboard, new-project form, and processing page are in the website. Symbol detection, tracing, the sketch, reports, and exports are not built. A screen that is not built says so. Contract coverage is tracked in `TRACEABILITY.md`.

## Tier 1

| ID | Feature | Status |
| --- | --- | --- |
| T1-01 | Upload a customer P&ID PDF and an instrument IO list Excel file | Tested |
| T1-02 | Detect whether a drawing is vector, scanned, or mixed | Tested |
| T1-03 | Detect equipment and IO instruments and keep their tags | Not started |
| T1-04 | Trace correct connections and flow direction | Not started |
| T1-05 | Draw duty/standby equipment as parallel lines | Not started |
| T1-06 | Lay the sketch out left to right, with minimal bends and no crossovers | Not started |
| T1-07 | Tag Check Report | Not started |
| T1-08 | Export SVG, PDF, and PNG | Not started |

## Tier 2

| ID | Feature | Status |
| --- | --- | --- |
| T2-01 | Confidence scores | Not started |
| T2-02 | Needs Review flags | Not started |
| T2-03 | Rule-based self-check with re-trace | Not started |
| T2-04 | Two-way click-to-trace side-by-side viewer | Not started |
| T2-05 | Connection Report | Not started |
| T2-06 | JSON export | Not started |
| T2-07 | Fuzzy tag matching | Not started |
| C1 | Speed-first path: caching, stage timings, and an early draft | Not started |
| C2 | Completeness safeguards: coverage check, symbol census, hidden-items ledger, orphan and dead-end check, two-direction trace, recall metric | Not started |
| C3 | Color-coded pipelines and a legend | Not started |
| A1 | Signal names on the sketch | Not started |
| A2 | HMI-ready SVG with tag ids | Not started |
| A3 | Verified badge | Not started |
| A4 | Multi-drawing results table | Not started |

## Tier 3

| ID | Feature | Status |
| --- | --- | --- |
| C9 | Keep as is / Modify | Not started |
| C5 | Versioning | Not started |
| C6 | Connection List Excel, an in-app grid, and validated re-import | Not started |
| C7 | Edit tools: delete, add, reverse, and recolor | Not started |
| C8 | Crossing control | Not started |
| C4 | Print-ready PDF | Not started |

## Tier 4

| ID | Feature | Status |
| --- | --- | --- |
| B1 | Sanity warnings | Not started |
| B2 | Detail-level slider | Not started |
| B3 | Revision compare | Not started |
| B4 | Ask the graph | Not started |
| B5 | Simulation mode, labeled SIMULATION | Not started |

## Stretch

| ID | Feature | Status |
| --- | --- | --- |
| S1 | Flow animation | Not started |
| S2 | Few-shot symbol matching | Not started |
| S3 | Optional one-slide PPTX | Not started |
| S4 | Batch upload | Not started |
| S5 | Dark theme | Not started |

## Future

| ID | Feature | Status |
| --- | --- | --- |
| FUT-01 | Multi-sheet P&IDs | Not started |
| FUT-02 | HMI integration | Not started |
| FUT-03 | Approval workflow | Not started |
| FUT-04 | More diagram types | Not started |
