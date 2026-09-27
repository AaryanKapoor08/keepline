# Engineering guide (for humans and agents)

- Python 3.13, standard library first. Allowed deps: numpy, pandas, pyyaml, streamlit, altair, matplotlib,
  anthropic, snowflake-connector-python, pytest. Ask the coordinator before adding anything else.
- Type hints everywhere; dataclasses from `keepline.contracts`; `from __future__ import annotations`.
- Small, pure functions; I/O at the edges; no global mutable state except cached singletons.
- Deterministic: every random choice takes a seeded `random.Random(seed)`. Same seed -> byte-identical output.
- Every pipeline stage has a deterministic no-LLM path. LLM calls go through `keepline.llm.get_llm()` only
  (it caches to disk). Never call an LLM in tests.
- Never read `data/truth` or `data/questions` outside `keepline/data` and `keepline/eval`.
- Tests: `pytest -q`, fast (<30 s total), use small in-memory fixtures, not the full generated dataset.
- Logging via `logging.getLogger(__name__)`; CLIs use `argparse` and print a short summary at the end.
- Docstrings explain *why*; comments are rare and useful. Match surrounding style.
- Windows dev box: use `pathlib`, UTF-8 explicitly on every file open.
- Language: "receipts, not clones". Never write product copy that implies simulating a person.
