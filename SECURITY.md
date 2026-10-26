# Security and permission notes

## Helper behavior

`scripts/diffproof.py inspect` is local and read-only:

- It invokes a fixed set of Git inspection commands with argument arrays (no shell command string), disables optional Git locks and filesystem-monitor hooks, and checks status, diff names, and whitespace.
- Its Python inventory reads only selected manifest/config files below the requested repository root. A manifest or workflow-directory symlink resolving outside that root is ignored. Git itself reads the repository metadata needed for status and diff inspection; a linked worktree may keep that metadata outside the working directory.
- It does not run project scripts, install packages, invoke GitHub, contact the network, read environment-variable values, or write to the repository.
- It emits paths, candidate command names, status labels, and limited Git diagnostic output to stdout. Review that output before sharing it.
- It times out Git inspection commands. A timeout or unreadable repository is `UNKNOWN`, not `PASS`.

## Limits

The helper is not a security scanner. Candidate risk indicators are heuristic and may miss harmful behavior or flag harmless commands. Project tests and build scripts execute project-controlled code when run by an agent. Inspect their definitions and consequences first; ask before checks that mutate data, reach external services, deploy, publish, upload, or incur cost.

The Skill itself cannot enforce permissions granted by an agent host. Do not grant more filesystem, shell, network, credential, or GitHub access than the task requires. Agensi's automated scan and manual review are still required, and neither is a guarantee that a skill is risk-free.

## Pre-submission review status

- Source-level review: performed locally for this release candidate. The helper has no network client, environment-variable reads, credential literals, shell-string execution, or GitHub mutation calls. Its only child processes are fixed Git inspection commands; the test harness uses temporary Git fixtures and deterministic status-classification cases.
- Symlink boundaries: tests confirm manifest and workflow-directory links resolving outside the requested root are ignored.
- Package contents: the ZIP contains text source/docs/tests only; no `.git`, bytecode cache, binary, or rights-hold memo is included.
- Automated Agensi scan: **NOT RUN**; no upload was made.
- Agensi human approval: **NOT RUN**; no listing was submitted.
- Secret scanning/SAST by a dedicated security product: **NOT RUN**.
