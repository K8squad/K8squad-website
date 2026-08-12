---
title: "ISI-2290 — Anthropic AUP/ToS posture for BYO-subscription Claude Code"
author: Research Engineer
date: 2026-08-12
issue: ISI-2290
parent_spike: ISI-2112
status: research-complete-pending-owner-signoff
decision_owner: CEO/Henrik or legal
gates_affected: [Epic 3, Epic 4, Epic 5, Epic 7]
---

# ISI-2290 — Is one Pro/Max sub powering a multi-agent product AUP-compliant?

## TL;DR — **No. Do not pool agents on one company Pro/Max sub. It is not defensible.**

The research does not support the spike's "gray area" framing for the *pooled*
case. Pooling many agents on a **single company Pro/Max subscription** violates
the Anthropic **Consumer Terms** on at least three independent grounds. The only
compliant models are:

1. **BYO-per-human-seat** — each end user runs Claude Code as *their own personal
   tool* on *their own* Pro/Max subscription + own token. Defensible for personal
   productivity use; carries a **residual commercial-use risk** that needs a named
   owner's explicit risk acceptance.
2. **Anthropic API key under Commercial Terms** — the clean, unambiguous path for
   anything Anthropic considers a "product/service for your customers." Metered
   per-token, no shared limits, and *explicitly permitted* to power products.
3. **Claude Team plan** — the sanctioned multi-*human*-seat path (min. 5 seats),
   still Consumer-style usage, not a fleet-of-agents license.

**Recommended constraint to record:** the credential stories (Epics 3/4/5/7) must
implement **BYO-per-human-seat only** (Model B `CLAUDE_CODE_OAUTH_TOKEN`, one
token per human's own subscription). **No shared/company-pooled subscription.**
For any first-party hosted/commercial serving, route through **Anthropic API keys
under Commercial Terms**, not a consumer subscription.

---

## The governing documents

| Plan / access | Governing terms |
|---|---|
| Claude Pro ($20/mo), Claude Max ($100–200/mo), claude.ai web, Claude Code on a subscription | **Consumer Terms of Service** + **Usage Policy (AUP)** |
| Anthropic **API key** | **Commercial Terms of Service** + Usage Policy |
| Claude **Team** | Team/Commercial-style terms; multi-human-seat |

Pro/Max — the subscriptions in question — fall under the **Consumer Terms**.

## Why pooling agents on one company sub fails (Consumer Terms)

Three independent clauses each defeat the pooled model:

**1. No sharing / no making the account available to others — Section 2**
> "You may not share your Account login information, Anthropic API key, or Account
> credentials with anyone else or make your Account available to anyone else."

A fleet of agents (or many users) driven by one company subscription's token is
"making your Account available to anyone else." Direct hit.

**2. No automated access except via API key — Section 3 ("Use of our Services")**
> "Except when you are accessing our Services via an Anthropic API Key or where we
> otherwise explicitly permit it, to access the Services through automated or
> non-human means, whether through a bot, script, or otherwise."

Automated/programmatic access on a *subscription* is prohibited **unless** it is
the narrow "explicitly permit" carve-out. Anthropic's own Claude Code CLI docs
(piping logs/diffs, official GitHub Actions on cron) are the strongest argument
that **the CLI as a personal tool** is that permitted automation — but that
argument covers an individual using their own CLI, **not** a hosted fleet serving
others.

**3. No commercial/business use — Section 11**
> "You agree that you will not use our Services for any commercial or business
> purposes ..."

Productizing a fleet on a consumer sub is squarely commercial/business use.

**AUP reinforcement:** the Usage Policy's "Do Not Abuse our Platform" section
prohibits coordinating activity across accounts to circumvent guardrails and
using automation to create accounts / evade limits. A Feb 2026 update frames
subscription limits as assuming **"ordinary, individual usage"** — i.e. consumer
plans are explicitly *not* designed for production/commercial automation.

## Why the two compliant paths hold

**Commercial Terms (API key) — explicitly permits productizing:**
> Section A.1: "Anthropic gives Customer permission to use the Services, including
> to power products and services Customer makes available to its own customers and
> end users."
Outputs are Customer-owned (Section B). Only hard limit: don't build a *competing*
model/service or resell the API without approval (Section D.4). This is the
unambiguous path for first-party hosted serving.

**BYO-per-human-seat (Consumer) — defensible, with a caveat:**
Each user runs Claude Code on **their own** subscription/token, for **their own**
work. This leans on the Section-3 "explicitly permit" CLI carve-out and keeps each
account single-user (satisfies Section 2). **Residual risk:** Section 11's
"no commercial or business purposes" + the "ordinary, individual usage" language
mean that if we *position and sell* the product as a business tool riding on users'
consumer subs, that posture is not risk-free. This is the exact call that needs
CEO/legal sign-off — it is a **risk-acceptance decision, not a technical one.**

## Recommendation (for owner sign-off)

- **REJECT** company-pooled single-subscription for the fleet. Record as a hard
  constraint on Epics 3/4/5/7.
- **ADOPT** BYO-per-human-seat (Model B token, one per user's own sub) as the
  self-hosted/BYO credential model — with CEO/legal accepting the residual
  consumer-commercial-use risk, documented.
- **DIRECT** any first-party/hosted/managed serving to **Anthropic API keys under
  Commercial Terms** (or offer it as a deployment option), which removes the ToS
  ambiguity entirely.
- **Offer Claude Team** as the sanctioned path if the goal is multiple *humans*
  under one org rather than a fleet of agents.

## Owner & next step

**Owner needed:** CEO/Henrik or legal (as stated in the issue). The research is
complete; what remains is a **risk-acceptance decision** on the BYO residual risk
and confirmation of the recorded constraint. Routed to the owner via a
`request_confirmation` interaction on ISI-2290.

## Sources
- Anthropic Consumer Terms of Service — anthropic.com/legal/consumer-terms (§2, §3, §11)
- Anthropic Usage Policy (AUP) — anthropic.com/legal/aup ("Do Not Abuse our Platform")
- Anthropic Commercial Terms of Service — anthropic.com/legal/commercial-terms (§A.1, §B, §D.4)
- Community analysis of Claude Code CLI vs subscription ToS (autonomee.ai) — corroborates CLI-as-personal-tool carve-out and "use API keys for products" guidance
- Parent spike: docs/bmad/research/spike-isi2112-claude-headless-token.md (ISI-2112)
