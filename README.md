# K8squad Website & Documentation

Source content for the K8squad website and documentation — the Kubernetes-native control plane for
running squads of AI agents.

## Structure

```
content/landing.md      Landing page copy (hero, features, how-it-works, CTAs)
docs/                   Documentation content (Markdown + frontmatter)
  index.md              Docs home
  quickstart.md         Install-to-first-squad in <30 minutes
  concepts/             Core concepts: Squads, Agents, Roles, Skills, Projects, Runs
  operator-guide/       Install, configuration, credentials, RBAC, settings
  author-guide/         Compose CRDs, manage work items
  console-guide/        Screen-by-screen console walkthrough
  api-reference/        API structure (CRD reference auto-generated from Go types)
  observability/        OTelConfig, metering, dashboards, tracing
  troubleshooting.md
  plugin-sdk/           Plugin overview, event reference, hello-world, examples
CONTENT-NOTES.md        Content ↔ Design handoff (branding, image slots, screenshot mapping)
```

## Format

All pages are framework-agnostic Markdown with YAML frontmatter (`title`, `description`,
`sidebar_position`). They drop into Docusaurus, Astro Starlight, Hugo, or a similar static-site
generator with minimal reshaping. Internal links are relative.

## Contributing content

- **Copy & structure** are owned by the Content Writer.
- **Visual design, hero art, logo lockups, and finalized console screenshots** are owned by the
  Graphic Designer — see [`CONTENT-NOTES.md`](./CONTENT-NOTES.md).
- The **API reference** field tables are generated from the `ksquad.io/v1alpha1` Go types at build time.

## Brand

Prose uses **"KSquad"**; the wordmark renders the stylized **"K8squad"** 8-Crest mark. Dark theme is
primary; single accent is Squad Azure `#3D7DFF`. Full brand contract in `CONTENT-NOTES.md`.
