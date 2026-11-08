# deepset/prompt-injections (third-party data)

- **Files:** `train-*.parquet` (546 rows), `test-*.parquet` (116 rows). Columns: `text` (string),
  `label` (int: 0 = benign, 1 = injection). Train 343/203, test 56/60 (benign/injection).
- **Source:** https://huggingface.co/datasets/deepset/prompt-injections
- **Revision:** `4f61ecb038e9c3fb77e21034b22511b523772cdd` (downloaded 2026-11-09, unmodified)
- **Licence:** Apache-2.0 (the dataset's repository licence tag; one metadata field also lists
  CC-BY-4.0). Both are permissive and require only attribution.
- **Content:** direct prompt-injection attempts (instruction override, system-prompt leakage,
  role-play personas) and benign requests, in English and German.

Used as a labelled evaluation set for the D1 injection detector (regex and LLM variants):
`python -m testbed.defenses.detector_eval`. Not converted into app-specific attacks here, because
the prompts are generic and do not target this app's planted canary or tools.
