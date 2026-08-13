# Content → Design Handoff Notes

**From:** Content Writer · **To:** Graphic Designer · **Re:** KSquad website + docs content

This file is the coordination contract for the KSquad website. **I own the copy and structure; you own
the visual design, hero art, logo placement, and the finalized console screenshots.** Everything below
is where the two meet.

---

## 1. What I delivered (this repo)

```
content/landing.md                 Landing page copy (hero, features, how-it-works, CTAs, microcopy)
docs/index.md                      Docs home
docs/quickstart.md                 Install-to-first-squad in <30 min
docs/concepts/                     Squads, Agents, Roles, Skills, Projects, Runs (+ index)
docs/operator-guide/               index, install, configuration, credentials, rbac, settings
docs/author-guide/                 index, compose-crds, work-items
docs/console-guide/index.md        Screen-by-screen walkthrough (needs your screenshots)
docs/api-reference/index.md        API structure (CRD tables auto-generated from Go types)
docs/observability/index.md        OTelConfig, metering, dashboards
docs/troubleshooting.md
docs/plugin-sdk/                   index, event-reference, hello-world, examples
```

All copy is framework-agnostic Markdown with frontmatter (`title`, `description`, `sidebar_position`),
so it drops into Docusaurus, Astro Starlight, Hugo, or similar. Internal links are relative.

---

## 2. Brand rules (please enforce in the visual layer)

- **Logo:** the official **v2 8-Crest** mark is the primary logo — app icon, nav-rail lockup, login /
  mobile splash, favicon. Source assets: `docs/bmad/branding/assets/` in the ksquad repo (built from
  `branding/src/`). Use `mark-8crest-on-dark` on dark, `mark-8crest-on-light` on light.
- **Wordmark vs prose:** the wordmark renders **"K8squad"** (numeral 8 in Squad Azure `#3D7DFF`). My
  running prose uses **"KSquad"** — this is intentional and matches the branding guideline. Please keep
  the wordmark stylized and leave the prose as written.
- **Palette (dark is primary):** canvas `#0B1220`, surface `#131D31`, border `#25324B`; text ramp
  `#7E8CA6 / #B6C3D8 / #E8EEF9`; **single accent** Squad Azure `#3D7DFF` (interactive + focus + brand).
  Status hues (`#34D399` running/ok, `#FBBF24` attention, `#FB7185` failed, `#A78BFA` memory events)
  are **reserved** — never chrome, always paired with an icon + label.
- **Type:** Geist Sans (UI/headings), Geist Mono (anything you could `kubectl` — CRD YAML, Run IDs,
  timestamps, secret refs, logs).
- **Taste guardrails:** no AI-purple gradients, no default Inter, no beige/brass; violet only as the
  memory-event tag. Border-forward, low-elevation "NOC density," not glossy SaaS.

Full contract: `docs/bmad/branding/branding-guidelines.md` and `docs/bmad/ux/README.md` in the ksquad repo.

---

## 3. Landing page — visual slots I left for you

| Location in `content/landing.md` | Suggested visual |
|----------------------------------|------------------|
| Hero | 8-Crest over dark NOC canvas, **or** the squad-overview console framed on a device |
| "How it works" band | 4-node horizontal flow: Install → Agents → Squad → Run |
| Feature cards (7) | One small azure-line glyph per feature (optional) |
| Trust/openness band | Apache-2.0 badge, GitHub star CTA |

Copy is written to stand on its own if a slot ships without art — nothing depends on an image to make
sense.

---

## 4. Console Guide — screenshot mapping (the big one)

`docs/console-guide/index.md` references screenshots as `./images/<name>.png`. **You own capturing,
annotating, and placing the final screenshots.** Source mocks live in the ksquad repo at
`docs/bmad/ux/images/`. Suggested source → target mapping:

| Doc image tag (`docs/console-guide/images/…`) | Source v6 mock (ksquad `docs/bmad/ux/images/`) |
|-----------------------------------------------|------------------------------------------------|
| `17-login.png` | `17-login-light.png` |
| `13-nav-ia.png` | `13-nav-ia-light.png` |
| `16-adaptive-nav.png` | `16-adaptive-nav.png` / `-light.svg` |
| `08-fleet-dashboard.png` | `08-fleet-dashboard.png` |
| `01-squad-overview.png` | `01-squad-overview.png` |
| `02-run-stream-sse.png` | `02-run-stream-sse.png` |
| `03-artifact-inspection.png` | `03-artifact-inspection-light.svg` |
| `06-build-browser.png` | `06-build-browser.png` |
| `19-project-dashboard.png` | `19-project-dashboard.png` |
| `14-project-tickets.png` | `14-project-tickets-light.svg` |
| `07-discussion-room.png` | `07-discussion-room.png` |
| `10-agent-runs.png` | `10-agent-runs.png` |
| `20-agents-role-org.png` | `20-agents-role-org-light.png` |
| `21-agents-leadership-org.png` | `21-agents-leadership-org.svg` |
| `09-team-organization.png` | `09-team-organization.svg` / `-light.png` |
| `11-team-configuration.png` | `11-team-configuration.svg` / `-light.png` |
| `05-credential-auth-state.png` | `05-credential-auth-state.png` |
| `15-users-roles.png` | `15-users-roles.png` |
| `18-mobile-rbac.png` | `18-mobile-rbac-light.svg` |
| `12-settings.png` | `12-settings.png` |

Notes:
- Some mocks currently exist only as `-light` or `.svg` — please normalize to the dark theme
  (dark is the primary console theme) and to consistent filenames/dimensions.
- If a screen's caption in the doc doesn't match your latest mock, ping me and I'll adjust the copy —
  **copy follows the real UI**, not the other way around.

---

## 5. Content guardrails I followed (so you can trust the copy)

- **End-user voice only.** No internal process references (no ISI-#### issue numbers, no BMAD, ADR/OQ
  jargon, no "spike-gated"). If you spot any leak, flag it — it's a bug.
- **Accurate to the architecture** as of 2026-08-13: CRD names/fields, Run phases, credential model,
  RBAC (2 global roles / 3 per-project access levels), install/exposure, `OTelConfig`, and the
  Postgres-stores-NATS-flows plugin model all match the source design.
- **`v1alpha1`** is the API group throughout.

---

## 6. Open coordination items

1. **Screenshots** — your call on capture vs. rendering the mocks; mapping above.
2. **Hero art direction** — happy to tweak the hero headline/subhead to fit whatever composition you
   choose.
3. **Sidebar / IA** — `sidebar_position` frontmatter encodes my suggested order; adjust freely to fit
   the site generator you pick, and tell me if section titles should change.
4. **Site generator** — not chosen here. Copy is portable; frontmatter may need light reshaping for the
   final generator.

Ping me on ISI-2367 when you've picked a direction and I'll align copy to it.
