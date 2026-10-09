---
name: quant-requirement-workflow
description: Define and deliver product requirements for the Lightning A-share and US-equity quantitative trading platform. Use for feature ideas, PRDs, prototypes, technical research, design, implementation, or changes to an existing requirement; skip general questions and unrelated maintenance.
---

# Quant requirement workflow

Work at the stage the user requested. If the user is only discussing an idea or explicitly says not to start, keep the work in chat. If implementation is requested, prepare the relevant requirement artifacts before coding and keep them aligned with the result.

This is a small internal platform. The current starting scope is A-share and US-equity daily strategies with broker adapters; high-frequency trading is a later possibility. Treat these as current context, not permanent requirements. Keep documents short enough for the actual change.

## Find or create the requirement

1. Check `docs/requirements/` for an existing requirement covering the request. Update it instead of opening a duplicate. For a new requirement, choose an unused `REQ-...` identifier and create `docs/requirements/【需求编号】/README.md` from `docs/templates/requirement-index.md`.
2. Keep the index as the entry point. Link only artifacts that exist, using relative links. Update status, important decisions, and changes as the work progresses.

## Turn an idea into a PRD and prototype

1. Preserve the original idea. Identify who has the problem, when it occurs, what they do today, what outcome they need, and which boundaries are already known. Check existing project context before asking questions. Separate facts from assumptions; ask only about unknowns that would change the scope or acceptance criteria.
2. Draft one normal user flow and the important failure flows. Convert each meaningful step or rule into a numbered, observable requirement: condition or action → system response → how to check it. Check that every goal is covered and remove details that prescribe an implementation without a product reason.
3. Use `docs/templates/prd.md` to write `prd.md`. Record scope exclusions, dependencies, and open questions without filling gaps with invented facts. For a user interface, derive prototype screens and feedback states from the flows, then create or link a reviewable prototype. For a backend-only change, mark the prototype as not applicable. Put its link in the PRD and index.

## Derive and research the technical solution

1. For each important PRD requirement, identify required data, state changes, external dependencies, failure behavior, and how to verify the result. Group the work into modules and interfaces; map the requirement identifiers to that design in `technical-design.md`, based on `docs/templates/technical-design.md`.
2. Research only decisions with meaningful alternatives or uncertainty. State the decision question and must-have criteria before choosing candidates. Compare viable options using current primary documentation, provider terms, and focused experiments when a decisive point cannot be established from documents. Record links, check dates, verified limits, trade-offs, and unknowns. Keep short research in the technical design; use a separate linked record only when the evidence is substantial. Do not present an untested assumption as a measured result.
3. For trading or market data, check the applicable market rules, broker API permissions and limits, data usage rights, order and account states, risk controls, and reconciliation. Address the markets involved in this requirement. Design for the stated daily-frequency need; note a future high-frequency boundary only when it changes today's interfaces.
4. Explain the selected design, key data and interfaces, failure recovery, tests, and a safe way to enable or revert it. If an existing choice is sufficient, record that briefly instead of manufacturing a comparison or proof of concept.

## Implement and close out

When development is in scope, implement against the PRD and design, then verify the acceptance criteria. Record actual test environment, cases, results, and remaining limits in a concise test report. Link the report and any release record from the requirement index. If implementation changes the agreed behavior or design, update the affected documents in the same work.

Do not invent approvals, test results, vendor permissions, or regulatory conclusions. Keep the user's explicit stage boundary and any existing authorization in force.
