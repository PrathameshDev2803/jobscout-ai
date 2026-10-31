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
