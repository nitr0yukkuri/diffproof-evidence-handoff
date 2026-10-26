# Agensi Listing Draft — English

This is a draft for a future listing, not a submission. The marketplace name must be checked for uniqueness in Agensi's form before any listing is attempted.

## Name

DiffProof — Evidence-Based Change Handoff

## Summary

Turn an AI-authored change into an evidence-backed, review-ready handoff. Discover repository-native checks, report honest run states, expose unverified risks, and draft a PR summary—without committing, pushing, merging, or running discovered project commands automatically.

## Description

DiffProof is a close-out workflow for AI coding agents after implementation. It starts from the repository's own instructions, the requested change, and the actual Git diff—not a hard-coded language checklist. It looks for likely verification commands in project manifests, scripts, Makefiles, and CI, then requires the agent to inspect those command definitions before running anything. Its optional, dependency-free helper inventories Git state and common Node.js/TypeScript, Go, Python, and Rust project files; it does not execute project checks.

For each selected check, DiffProof asks the agent to record the exact command, observed exit status, and evidence. It keeps `PASS`, `FAIL`, `SKIPPED`, `NOT RUN`, and `UNKNOWN` distinct to make unsupported success claims easier to catch. Agent adherence is not deterministic, so evaluate the workflow with the agents you use before relying on its output. The final handoff summarizes what changed and why, what actually ran, what remains unverified, residual risks, documentation/design impact, and decisions that belong to a human. It can also draft—but never post—a pull request description.

DiffProof does not certify correctness, replace CI or human review, or perform commits, pushes, merges, deployments, or GitHub mutations. It does not contact external services or install dependencies. The agent still needs access to the repository and to any local commands a user explicitly chooses to run.

## See it in action (sample request and result)

**Request**

> I finished the retry change. Prepare a review-ready handoff. Use the checks already configured in this repository. Do not push, create a PR, or merge. If a command could change data or contact a service, stop and ask me first.

**Result**

> **Change:** Added bounded retries for transient payment-provider timeouts and kept the existing idempotency key. No unrelated files were changed.
>
> **Verification:** `npm run lint` — PASS (exit 0; no diagnostics). `npm test -- retry` — PASS (exit 0; 8 tests reported, including timeout and duplicate-request cases). `npm run build` — NOT RUN; this command was not needed for the requested test-only change and was not run.
>
> **Not verified:** The staging integration suite was SKIPPED because it would contact a non-local payment service; it was not authorized. `git diff --check` — PASS (exit 0).
>
> **Risks:** The local tests do not prove the provider's live retry headers match the assumptions. The staging behavior remains unverified.
>
> **Human decision:** Decide whether to run the staging integration suite and review the provider-specific retry policy before merge.
>
> **PR draft (not posted):** Add bounded retries for transient provider timeouts. Local lint and retry tests pass; staging integration remains unverified pending authorization.

The example is illustrative. DiffProof never invents these commands or outcomes; they must come from the target repository and a fresh run.

## Compatibility note

Works with Agent Skills-compatible agents that can read repository files and, when authorized, run local commands. Optional helper requires Python 3.9+ and Git. No agent-specific API or plugin installation is required.

## Categories and tags

- Primary category: Testing & Debugging
- Additional categories: Code Quality & Review; Agents & Orchestration
- Tags: verification, evidence, pull requests, coding agents, TypeScript, Go, Python, Rust

## Limitations

- Agent adherence is not deterministic; evaluate it with the agents and repositories you use.
- The helper inventories known project files and uses lightweight risk hints; it is not a full parser, test runner, security scanner, or proof of correctness.
- A check can pass while the change is still wrong. Human review and required CI remain necessary.
- No license, contributor ownership, or revenue allocation is asserted by this draft.
