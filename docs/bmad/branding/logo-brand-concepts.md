---
title: K8squad logo — brand concepts & visual directions (Brainstormer handoff)
author: Brainstormer (Mary) — IsItObservable Labs
date: 2026-08-10
source_ticket: ISI-2137
phase: BMAD Phase 1 — Analysis (brand ideation)
hands_off_to: Graphic Designer (execute SVG + PNG)
coherence_anchor: docs/bmad/ux/README.md (ISI-2126 console visual system)
note: BMAD artifact — gitignored, never committed to the GitHub repo. Logo *outputs*
      (SVG/PNG) go to assets/logo/ per the ticket; this brief does not.
---

# K8squad Logo — Brand Concepts & Visual Directions

> **What this is.** The Brainstormer half of ISI-2137: brand concepts, name associations,
> visual metaphors, mood-board directions, and a palette — the creative brief the Graphic
> Designer executes into SVG + PNG. Three directions, one recommendation, one shared palette.
>
> **The single most important constraint (discovered, not assumed).** K8squad is **not a
> greenfield brand in a vacuum** — an operator-console visual system already shipped (ISI-2126).
> The logo must read as a **sibling** of that system, not a stranger. That decision cascades
> through everything below: same azure, same geometric restraint, same "developer tool, not
> AI-startup" posture.

---

## 1. Brand DNA — what the mark has to say in one glance

| Signal | Why it must be present | Source |
|---|---|---|
| **Kubernetes family** | Instant "this belongs with k8s / k9s / k3s / kro". The `K8s` root is half the name. | Ticket; k8s naming convention |
| **Squad / team** | A *plurality* of agents acting as one unit — the product's whole thesis (Team CRD, squads). | ISI-2117 Theme A |
| **Coordination / orchestration** | Agents don't just coexist, they're *in formation* — deliberate, not a random mesh. | ISI-2117 Themes A/B |
| **Operator-grade, not toy** | Calm, dense, legible; a control-plane, not a chatbot. Matches the console's NOC posture. | ISI-2126 principle 1 |

**What it must NOT say** (anti-brief — these are the clichés to actively dodge):
- ❌ A literal copy of the k8s helm/wheel (derivative, legally awkward, invisible-at-16px).
- ❌ Generic "AI" tropes: neural-brain, glowing orb, purple gradient, sparkle. The console
  taste-doc explicitly bans AI-purple gradients / default Inter / beige-brass — the logo inherits that ban.
- ❌ A random node-mesh (says "generic distributed system", not "*squad* with intent").
- ❌ Robot faces / android mascots (dates instantly, breaks at favicon).

---

## 2. Name associations — mining "K8squad" for glyphs

The name is unusually rich. Three exploitable seams:

1. **The shared `8`.** `K8s` and `K8squad` share the `8` glyph. The `8` is a *numeronym*
   (K-ubernete-s → K-8-s, eight elided letters). It is the literal hinge between "Kubernetes"
   and "squad." → **The `8` is the family crest.** Owning it ties lineage + name in one figure.
2. **`quad` inside `squad`.** "Squad" contains "quad" (four). A squad reads naturally as a
   *small* tactical unit — four to seven agents, not a swarm. Supports "a handful of agents in
   formation," and echoes k8s' own seven-spoke motif without copying it.
3. **Squad = jersey/roster energy.** Sports-team semantics: formation, a number, a huddle, a
   bracket around a roster. Developer-friendly, human, warm — a counterweight to "control-plane."

Wordmark spelling to lock with the Designer: **`K8squad`** (capital K, numeral 8, lowercase
`squad`) — mirrors `K8s` casing and the ticket title. The `8` gets typographic emphasis.

---

## 3. Three visual directions

Each direction: the metaphor · the mark · why it fits the k8s family · favicon→banner behavior · risk.

### Direction A — **"Squad Formation"**  *(recommended)*
- **Metaphor:** agents as distinct nodes arranged in a *deliberate formation* — a chevron / huddle /
  wedge — not a random graph. Coordination is shown by the *arrangement itself*, optionally with
  thin connectors (A2A interoperability). "A team that moves as one."
- **The mark:** 4–5 rounded square/circle nodes (CRD-square nods to Kubernetes objects) locked into
  a formation that *reads as a `K`* in negative space, or as a compact squad-wedge inside a rounded
  container (the "cluster boundary"). One node is the front/lead (coordination), the rest fall in
  behind it — same azure, tint-differentiated, so they read as *one team, distinct members.*
- **k8s-family fit:** squares = k8s objects; container ring = cluster/namespace; azure = the
  "Kubernetes-native nod" already chosen for the console. Sibling to k9s/k3s without imitating the helm.
- **Favicon→banner:** at 16px collapses to 3 nodes in a wedge (still legible as "a small team");
  at banner adds connectors + wordmark + tagline. **Best small-size survivability of the three.**
- **Risk:** node-clusters are common in cloud-native branding → *formation intent* + CRD-squares +
  the negative-space `K` are what make it ownable. Designer must push the formation to feel composed,
  not scattered.

### Direction B — **"The 8-Crest"**  *(most memorable as an avatar)*
- **Metaphor:** make the shared `8` the hero — the family crest. The `8` as two linked huddles /
  two orbits of agents / a container whose two loops each hold a squad. The numeronym story (8 =
  Kubernetes lineage) and the squad story fuse into one glyph.
- **The mark:** a geometric `8` built from agent nodes or from two rounded-square loops; agent dots
  sit on/inside the loops. Can double as an infinity-adjacent "continuous coordination" read without
  being a literal ∞ cliché.
- **k8s-family fit:** *directly* encodes the `K8s` heritage via the numeral it shares — the most
  literal lineage claim of the three, while staying our own shape (not the helm).
- **Favicon→banner:** **strongest favicon** — a single bold `8`-mark is unmistakable at 16px and as
  a circular GitHub-org avatar. Banner pairs the crest with `K8squad` wordmark.
- **Risk:** an `8` can read as "figure-eight/loop/infinity" if under-designed; must be unmistakably a
  *squad container*, not a racetrack. Keep it a crest, not an outline.

### Direction C — **"Helm, Re-crewed"**  *(heritage-forward, highest-risk)*
- **Metaphor:** honor the Kubernetes helmsman lineage *explicitly* but pluralize it — the single
  ship's-wheel becomes a hub with a **squad** on the spokes. "One helm, many hands." Hub = the
  orchestrator/control-plane; spoke-ends = agents.
- **The mark:** a hub-and-spoke where each spoke terminates in an agent node (not a wheel rim). 4–5
  spokes (a *squad*, deliberately fewer than k8s' seven — a distinguishing, ownable choice).
- **k8s-family fit:** the *loudest* "we're Kubernetes-native" statement — reads as heritage on sight.
- **Favicon→banner:** hub-and-spoke can muddy at 16px and risks looking like the official k8s mark in
  a thumbnail — **weakest favicon**, needs a simplified 3-spoke favicon lockup.
- **Risk:** **highest** — closest to the official k8s wheel = derivative/legal-adjacent, and the
  console team deliberately *avoided* copying #326ce5 for exactly this reason. Include as the
  heritage option, but flagged: only pursue if the Designer can make it unmistakably *not* the k8s helm.

---

## 4. Shared palette — inherit the console, don't reinvent it

The console already locked its brand palette (ISI-2126). The logo **uses the same tokens** so the
mark and the product look like one thing. Do **not** introduce new hues.

| Role | Token | Hex | Use in mark |
|---|---|---|---|
| **Primary brand** | Squad Azure | `#3D7DFF` | the hero color — the "Kubernetes-native nod without copying #326ce5" |
| Squad tint (lead/highlight) | accentText | `#93B7FF` | differentiate the front/lead agent node |
| Squad tint (recede) | accentBg | `#16244A` | back-row nodes / low-contrast fill on dark |
| Logo-on-dark ground | canvas | `#0B1220` | primary lockup ground (dark is the console's primary theme) |
| Ink (logo-on-light) | canvas as ink | `#0B1220` | the mark reversed to near-black on white |
| Reverse / knockout | textHi | `#E8EEF9` | white-ish knockout for one-color-on-azure avatar |

**Palette rules for the mark:**
- **Squad = an azure-mono ramp** (`#16244A → #3D7DFF → #93B7FF`), so nodes read as *one team,
  distinct members* — this is the core visual idea and it stays single-hue on purpose.
- **Do NOT borrow the console's status hues** (green/amber/rose = Run state; violet = memory
  events). Those are *reserved semantics* — pulling them into brand chrome would break the system
  the console guards. The logo is azure-family only.
- Ship a **1-color** version (azure-on-white, white-on-azure, near-black-on-white) that survives
  GitHub avatar rings, favicons, stickers, and single-color print.

**Type:** wordmark in **Geist Sans** (the system UI/heading face) with the `8` emphasized; a
**Geist Mono** "terminal lockup" variant is a strong alt — it nods to k9s' terminal-UI sibling vibe
and the console's "mono for anything you could `kubectl`" rule. Set `squad` slightly lighter than
`K8` to make the numeronym hinge pop.

---

## 5. Mood-board directions (for the Designer's reference-gathering)

- **Cloud-native OSS family:** k8s, k9s, k3s, kro, Argo, Cilium, Crossplane wordmarks — geometric,
  flat, one or two colors, symbol-that-survives-a-favicon. *Aim: sit convincingly on that shelf.*
- **Formation / squad energy:** flight-formation chevrons, a rowing eight, a five-a-side lineup, a
  constellation with intent. *Composed, not scattered.*
- **Control-plane calm:** the console's own `00-visual-system` sheet — border-forward, low
  elevation, dense-but-legible. The logo is the console's front door; same temperature.
- **Anti-references (pin these as "NOT this"):** neural-net brains, glowing AI orbs, purple
  gradients, robot mascots, literal ship-wheels, generic random-node meshes.

---

## 6. Taglines (optional lockup line for the banner)

1. **"Kubernetes-native agent squads."** *(clearest — says what it is)*
2. **"Your agents, in formation."** *(shortest, on-metaphor, ownable)*
3. **"Orchestrate agent squads on Kubernetes."** *(verb-forward, SEO-friendly)*
4. **"Squads of agents. Native to the cluster."**

---

## 7. Recommendation & handoff

**Lead with Direction A ("Squad Formation")**, carry **Direction B ("8-Crest")** as the strong
avatar-first alternate, and include **Direction C ("Helm, Re-crewed")** only as the flagged heritage
option. A + B together give the Designer a system: **B is the symbol/favicon/avatar, A is the
expanded formation for banners and the horizontal lockup** — they can even converge (the 8-crest
*is* a two-row squad formation). That convergence is the sweet spot: one idea, two zoom levels.

**Deliverables to the Graphic Designer (ticket §Deliverables):**
- 2–3 concepts realized (A, B, +C if viable) — SVG source + PNG exports.
- Square (avatar) + horizontal (banner) variants; a favicon-simplified lockup.
- 1-color + reversed versions; on-dark (`#0B1220`) and on-light grounds.
- Palette per §4 (azure-mono, no status hues); type per §4 (Geist Sans/Mono).
- Must survive **16px favicon → README banner**.

**Open questions for the Designer / Henrik (non-blocking):**
- OQ1: square agent-nodes (CRD-object read) vs circles (softer/team read)? — leaning square.
- OQ2: Geist **Sans** vs **Mono** wordmark as primary? — Sans primary, Mono as the "terminal" alt.
- OQ3: is the parent GitHub org `K8squad/K8squad` (currently 404) the canonical home the avatar
  targets? Confirm before final export sizing.
