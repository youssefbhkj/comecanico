# MécaPilot — MVP

Diagnostic copilot for workshop technicians: reads OBD data (emulator), retrieves fault sheets,
lets an LLM form source-grounded hypotheses, guides tests, produces an HTML report.
Principle: the agent proposes, the technician decides. Talk to the user in French; code, identifiers and docs in English.

## Decisions (override the original specs; do not re-read specs unless needed)
Specs: `archi.md` (agent spec), `mecapilot_stack_rag.md`, `contexte11.md`. This file wins on conflicts.

- Two control levels: Python state machine (global) + bounded LLM tool-calling loop inside agentic states.
- States: COLLECTING (Python only: reads DTCs, freeze frame, VIN; technician enters symptoms) → entry gate
  (exact code lookup; safety sheet → STOPPED(safety); no sheet for the codes AND no symptoms → STOPPED(code_not_found);
  otherwise → ANALYZING; each read code without a sheet always shows the fixed "code absent de la base" message) → ANALYZING (LLM loop)
  ⇄ AWAITING_TEST_RESULT (human, no LLM) → AWAITING_CONFIRMATION (human) → REPORTING (Python) → COMPLETED.
  Also STOPPED(insufficient_documentation). The LLM never changes state or cause statuses.
- Tool allowlist per state; only ANALYZING is agentic: `list_sheets`, `search_docs`, `get_fault_sheet`, `read_pid`,
  `submit_analysis`. Search freedom: the LLM writes free-text queries, reformulates, chains searches, browses the
  catalog (`list_sheets`), and can restrict a search to given sheets. Finding a sheet ≠ applying it: a sheet covers a
  code only if the code is listed in it; the LLM never deduces anything about an absent code (no code similarity).
- Option B (overrides G2 stop): when a read code is absent, the LLM may still work from symptoms on sheets it finds.
  Python marks every hypothesis whose sheet covers none of the read codes as "symptom match — sheet does not cover
  the read code", shown to the technician.
  `submit_analysis` is the terminal tool, validated by guardrails; errors go back to the LLM as tool errors.
  `max_tool_iterations` in config. `clear_dtcs` is never exposed to the LLM (no workflow step in the MVP).
- Cause statuses (open/strengthened/weakened/eliminated/confirmed/disputed) are changed only by Python, from the
  sheet's test outcome table. The LLM selects, orders and explains causes. No probability levels.
- Guardrails on submit: cause exists in a sheet retrieved this session and is not eliminated; citations were returned
  by a tool this session; each hypothesis has ≥1 evidence ref (existing journal event) and ≥1 citation; proposed test
  exists and is not done; numbers in free text must exist in session values. Safety sheet in any tool result → stop.
- **No PID plausibility validation** (overrides archi.md §2.3, G5, stack_rag §2.2 `plausibilite`): measurements are raw
  (pid, value, unit, timestamp, source, event_id). The prompt tells the LLM never to claim measurements are validated.
- Knowledge: fault sheets are pure YAML with English keys (`data/sheets/SYN-*.yaml`); exact DTC lookup + keyword search.
  Citation id format: `SYN-001#causes`; cause ref `SYN-001:C1`; test ref `SYN-001:T1`.
- Report: HTML from the journal via Jinja2 template, no LLM call. Journal: JSONL, one event per line.
- LLM behind `LLMClient` protocol: `ClaudeClient` (haiku for dev, sonnet for demo) and `FakeLLM` (scripted tool calls).
- Postponed: embeddings/Chroma/BM25/RRF, voice, warranty/customer reports, code correlation, contradiction detection,
  repair verification, rule interpreters, python-OBD/bench hardware.

## Data rules
All automotive data is synthetic and labeled `synthetic: true` ("Synthetic cause A"). Never invent real automotive facts.

## Layout
`mecapilot/` app.py, models.py, agent/{states,loop,tools,llm,prompts}.py, acquisition.py, knowledge.py, engine.py,
guardrails.py, journal.py, report.py, templates/ · `data/` · `tests/` · `sessions/` (git-ignored)

## Commands
Use the project venv (Python 3.11): `.venv/Scripts/python -m pytest -q` ·
`.venv/Scripts/python -m pip install -r requirements.txt` · `.venv/Scripts/python -m streamlit run mecapilot/app.py`
