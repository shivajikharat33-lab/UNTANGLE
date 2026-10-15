# Hand-building an answer key

An answer key is the result you expect from one drawing. A person writes it before the app has node ids, so every connection uses tags.

Copy `TEMPLATE.json` and replace the example values. The example tags are only a shape to copy. They are not a customer drawing and they are not an app result.

## What to fill in

1. `drawing_id` — a short name for this drawing, such as the file name without the extension.
2. `expected_tags` — every instrument tag that must appear, with its signal when you know it. Leave `signal` as an empty string when the IO list has no signal.
3. `expected_equipment` — every equipment tag that must appear, with a short label such as "Feed pump".
4. `expected_connections` — each line that must appear.
   - `from` and `to` are tags.
   - `direction` is `forward` when flow runs from `from` to `to`, `reverse` when it runs the other way, `bidirectional`, or `unknown`.
   - `line_type` is `process`, `signal`, or `other`.
5. `expected_duty_standby_groups` — equipment that should be drawn as parallel duty/standby lines.
   - `member_tags` lists the equipment in the group.
   - `shared_upstream` and `shared_downstream` are tags of the equipment or instruments those members share.

Check the file against the contract by opening a Python shell in `backend/` and running:

```bash
python -c "import json; from pathlib import Path; from app.schemas.answer_key import AnswerKey; AnswerKey.model_validate(json.loads(Path('../data/answer_keys/TEMPLATE.json').read_text(encoding='utf-8'))); print('ok')"
```

Use the same direction words as an edge in `docs/CONTRACTS.md`.
