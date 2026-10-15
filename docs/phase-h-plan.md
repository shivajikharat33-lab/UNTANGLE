# Phase H plan

Warnings, answers, comparisons, and the evaluation table only read the graph. They do not add or remove a connection. Version 0 stays locked by the Phase G trigger.

## Already present

- Sanity warnings, detail-level redraw, job compare, template questions, simulation banner, and `python -m eval.run`.
- Flags `modify_enabled`, `ask_graph_llm_enabled`, and `fewshot_symbols_enabled`.

## This pass

- Ask box on the results page, with cited ids.
- A citation check that rejects a model answer naming an id that is not in the graph. The model switch stays off.
- Settings page reads the live flags. Transparency text comes from that response.
- Evaluation rows for a rotated variant and a held-out case. Metrics that were not measured are `n/a`.
- Stretch controls for theme, flow marks, batch upload, and few-shot suggestions. Each stays off unless its flag is true.

## Risks

- Cairo is still missing on Windows, so print stays on ReportLab.
- The harness does not time a customer drawing. There is no customer file in the repo.
