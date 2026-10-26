# DiffProof

**Evidence-Based Change Handoff for AI Coding Agents**

DiffProof helps an agent close out an implemented software change without guessing which checks apply or overstating what passed. It reads the repository's own conventions, manifests, CI references, and Git state, then helps the agent produce a reviewer-ready summary of the change, observed verification, unverified areas, risks, and human decisions.

It is designed for repositories that use Node.js/TypeScript/JavaScript, Go, Python, Rust, Make, or a mixture of ecosystems. Repository-defined checks take precedence over generic language defaults.

## What it does

- Inspects the requested scope, Git diff, staged/unstaged state, and untracked files.
- Finds likely check commands from project configuration and CI evidence, while labeling them as candidates rather than executing them.
- Requires the agent to inspect scripts and side effects before a check is run.
- Separates `PASS`, `FAIL`, `SKIPPED`, `NOT RUN`, and `UNKNOWN` to make unsupported success claims easier to catch. Agent adherence is not deterministic, so evaluate the workflow with the agents you use.
- Produces a concise change handoff and optional, unposted PR description.
- Leaves design decisions, risk acceptance, approvals, and merge decisions with people.

## What it does not do

DiffProof does not run project-defined tests automatically, prove a change correct, replace human review or CI, call GitHub, create PRs, or commit/push/merge. It is not a security scanner. The helper's risk indicators are reminders for review, not a security boundary.

## Use it

Install the folder containing `SKILL.md` in an Agent Skills-compatible agent, then ask:

> Use DiffProof to prepare an evidence-based handoff for the changes in this branch. Do not commit, push, create a PR, or merge.

The agent should inspect the project instructions and diff first. If the helper is available, run this read-only inventory from the DiffProof folder:

```sh
python scripts/diffproof.py inspect --repo /path/to/project
```

On Windows, use a valid local path, such as:

```powershell
python .\scripts\diffproof.py inspect --repo C:\path\to\project
```

To compare a known base commit/ref as well:

```sh
python scripts/diffproof.py inspect --repo /path/to/project --base origin/main
```

The helper prints JSON to stdout, writes no report or project file, makes no network requests, and never executes the discovered project commands. The agent must inspect the actual command definitions and ask before side-effecting checks.

## Example handoff

```text
Change
- Added CSV export for filtered records; unrelated files were not changed.

Verification
- npm run lint — PASS (exit 0; no diagnostics).
- npm test -- --runInBand — FAIL (exit 1; 1 assertion failed in export.spec.ts).
- git diff --check — PASS (exit 0; no whitespace errors).

Not verified
- Production build — NOT RUN; the repository's build requires signing credentials that are not available here.
- Windows packaging — SKIPPED; this run is on Linux and the Windows CI workflow was not executed.

Risks
- The failed export assertion is unresolved. No claim is made that export behavior is correct.
- Manual testing of large files and spreadsheet compatibility was not performed.

Human decisions
- Decide whether the spreadsheet compatibility limitation is acceptable before merge.

PR draft (not posted)
- Summary: Add filtered-record CSV export.
- Checks: lint PASS; test FAIL; diff check PASS.
```

The example illustrates the required honesty, not a promise that every project has these commands or environments.

## Requirements and compatibility

- Skill: any AI coding agent that can read the Agent Skills `SKILL.md` format and inspect/run commands available in its environment.
- Optional inventory helper: Python 3.9+ and Git. If either is unavailable, the workflow remains usable manually.
- No package dependencies, network access, GitHub token, model API key, or marketplace connection is required.
- Agensi handles one ZIP containing `SKILL.md` plus supporting text files. The package is a single skill, not an agent-specific plugin.

## Validation

Run the helper's standard-library tests from this directory:

```sh
python -m unittest discover -s tests -v
```

The tests cover status classification, clean/no-change and non-Git cases, command discovery from four language manifests, missing commands, malformed configuration, and risk-review indicators. They do not prove that a coding agent will follow the workflow; that requires evaluation with the target agents.

## License and rights

No redistribution license is included. This release candidate must not be listed or sold until the relevant contributors approve ownership, licensing, and revenue-sharing terms. Technical readiness is not publication or commercialization authorization.
