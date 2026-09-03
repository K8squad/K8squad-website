---
title: GitHub connect (repo access)
description: Give a KSquad agent access to a GitHub repository — GitHub App / OAuth, or a fine-grained Personal Access Token with the right scopes. What each path needs and how to pass the repo test-connection.
sidebar_position: 5
---

# GitHub connect (repo access)

Use this mode to give an agent a **GitHub repository** to work on. Unlike the model auth modes, this is
a **project** credential — it grants repo access (clone, read, and write branches/PRs), not model
inference. It does not appear in the model env-var table.

Two paths ship at v1:

- **GitHub App / OAuth** (recommended) — scoped, revocable, org-manageable
- **Personal Access Token (PAT)** — fastest to set up; use a **fine-grained** token with minimal scopes

## What you need

- A GitHub account with access to the target repository.
- Permission to install a GitHub App on the org/repo (for the App path), **or** the ability to create a
  Personal Access Token (for the PAT path).

## Option A — GitHub App / OAuth (recommended)

1. In the console, on the project's **Connect repo** step, choose **GitHub App / OAuth**.
2. Authorize the KSquad GitHub App and **select the specific repositories** it may access — grant the
   narrowest set that the agents need.
3. GitHub issues short-lived, repo-scoped installation tokens; KSquad stores the installation reference
   in your per-user Secret. You can revoke access any time from **GitHub → Settings → Applications**.

Prefer this path: access is **repo-scoped**, **revocable**, and **auditable at the org level**, and
there's no long-lived token to rotate by hand.

## Option B — Personal Access Token (PAT v1)

Use a **fine-grained** PAT (not a classic token) so you can scope it to a single repository.

1. Go to **GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens →
   Generate new token**.
2. **Resource owner:** your user or org. **Repository access:** *Only select repositories* → pick the
   target repo.
3. Grant the **minimum repository permissions**:

   | Permission | Access | Why |
   |------------|--------|-----|
   | **Contents** | Read and write | clone the repo, push branches/commits |
   | **Pull requests** | Read and write | open and update PRs |
   | **Metadata** | Read (mandatory) | required for any repo access |
   | **Workflows** | Read and write *(only if the agent edits `.github/workflows`)* | optional |

4. Set a **short expiry** and copy the token (`github_pat_...`) — it is shown once.
5. Paste it into the **Connect repo** PAT field, or create the Secret:

   ```bash
   kubectl create secret generic my-repo-token \
     --namespace ksquad-system \
     --from-literal=token='github_pat_...'
   ```

> **Scope discipline:** never use a classic PAT with broad `repo` scope for an agent. A fine-grained,
> single-repo token limits blast radius if it leaks, and a short expiry forces healthy rotation.

## Passing test-connection

The repo test-connection succeeds when:

- [ ] The credential (App installation or PAT) can **read the target repository**.
- [ ] For write actions (branches/PRs), it has **Contents: write** and **Pull requests: write**.
- [ ] A fine-grained PAT is scoped to the **correct repository** and **hasn't expired**.

A `404` on the repo usually means the token isn't scoped to it (fine-grained tokens return `404`, not
`403`, for repos they can't see); a `403` on push means missing **Contents: write**.

## Rotation and revocation

- **App/OAuth:** revoke or re-scope from **GitHub → Settings → Applications**; no manual token rotation.
- **PAT:** update the Secret with a new token — the Run auto-resumes when the Secret changes:

  ```bash
  kubectl create secret generic my-repo-token -n ksquad-system \
    --from-literal=token='<new-pat>' --dry-run=client -o yaml | kubectl apply -f -
  ```

## Related

- [Quickstart](../quickstart) — connect a repo end to end as part of your first Run
- [Operator Guide → Credentials](../operator-guide/credentials) — the credential model and rotation
