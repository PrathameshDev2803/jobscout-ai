# AGENTS.md

## Primary Directives for AI Agents

### 1. Continuous Live Deployment (Push Live on Update)
- **Mandatory Rule**: Whenever code, assets, or configuration updates are made and verified, immediately push them live to the remote repository.
- **Workflow**:
  1. Verify changes locally (syntax, imports, or test execution).
  2. Stage modified files:
     ```bash
     git add <changed-files>
     ```
  3. Commit with a concise, descriptive semantic commit message:
     ```bash
     git commit -m "<type>: <brief description of changes>"
     ```
  4. Push directly to the live remote:
     ```bash
     git push origin main
     ```
- **Guardrails**:
  - Never commit `.env`, session keys, API secrets, or private data.
  - Verify `git status` to ensure only intended changes are staged and pushed.

### 2. Risk-Based Execution Policy (Execution Efficiency)
To prevent 10+ minute execution delays on small tasks, scale verification strictly to risk level:

- **Tier 1: Low-Risk / Content-Only Changes** (copy, static labels, HTML text, docstrings):
  - **Target**: Locate exact string/component directly. Never run unbounded recursive scans.
  - **Verification**: Fast static check only (`python -m py_compile <file>`).
  - **Guardrail**: Do NOT run full test discovery, do NOT launch browser sessions, and do NOT investigate unrelated backend/database schemas.
- **Tier 2: Medium-Risk / Styling Changes** (CSS, layout adjustments, responsive classes):
  - **Target**: Inspect only the affected component and its scoped styles.
  - **Verification**: Check syntax and targeted DOM state for affected viewports only. Avoid unrelated browser exploration.
- **Tier 3: High-Risk / Functional Changes** (business logic, state machines, DB schema, auth):
  - **Target**: Inspect dependencies and affected workflows.
  - **Verification**: Run targeted unit tests (`.venv\Scripts\python.exe -m unittest <test_file>.py`). Expand to full test discovery only when cross-cutting risk justifies it.

### 3. Tool & Command Discipline
- **Search Boundaries**: Always exclude `.venv`, `.git`, and `__pycache__` on filesystem searches.
- **Test Runner**: Repository uses Python's standard `unittest` via `.venv\Scripts\python.exe` (not `pytest`).
- **PowerShell Safety**: Avoid complex multi-line inline strings with `<` or `&` inside `python -c` commands.
