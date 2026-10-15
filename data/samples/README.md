# Sample drawings

Put the real customer files in this folder on your own machine:

- the P&ID PDF
- the instrument IO list workbook (`.xlsx`)

These files are confidential.

- Do not commit them. Git ignores everything in this folder except this README.
- Do not push them to GitHub.
- Do not paste them into a public cloud AI tool, and do not upload them to a public chat.

Inspect a local file from the repository root:

```bash
python scripts/inspect_pdf.py data/samples/your-drawing.pdf
python scripts/inspect_excel.py data/samples/your-io-list.xlsx
```

If the file is not here yet, those scripts stop and tell you where to put it. They do not invent a drawing.
