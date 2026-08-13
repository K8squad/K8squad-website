---
title: RBAC & access levels
description: KSquad's human identity model — two global roles, three per-project access levels, first-run admin bootstrap, sessions, and the OIDC/SSO seam.
sidebar_position: 4
---

# RBAC & access levels

KSquad has **three distinct identity planes**, and it's worth keeping them straight:

1. **Human identity** — who's logged into the console (this page).
2. **Kubernetes workload RBAC** — what the operator's controllers may do in the cluster.
3. **Agent credentials** — the per-user Secrets agents authenticate with (see [Credentials](./credentials)).

This page is about plane 1: **user management and per-project RBAC**, a first-class part of KSquad.

## The model: two global roles + three per-project access levels

Authorization resolves at one choke point (deny-by-default), from two kinds of grant:

**Global roles** (on the user):

- **`admin`** — full control: defines Agents/Teams/Projects, manages users, assigns users to projects,
  manages credentials/plugins/settings, and sees the fleet-wide dashboard and *Users & Roles*.
- **`user`** — an ordinary account with no global powers; everything they can do comes from their
  per-project access levels.

**Per-project access levels** (on the membership — the UI labels this axis **"Access level"** to avoid
collision with the `Role` CRD):

| Access level | Read | Act & compose (edit CRDs, start/kill Runs) | Administer project membership/settings |
|--------------|:----:|:-----:|:-----:|
| **`viewer`** | ✅ | — | — |
| **`contributor`** | ✅ | ✅ | — |
| **`maintainer`** | ✅ | ✅ | ✅ |

Within an authorized project, **`maintainer` ⊃ `contributor` ⊃ `viewer`**. Access is held **per
membership**: a user can be a `maintainer` on one project and a `viewer` on another. Authorization
always resolves from the specific project membership, never a single global label.

- **`viewer`** is the least-privilege grant for auditors, stakeholders, and watchers — read-only
  access without over-granting write.
- **`contributor`** lets someone act and compose without being able to administer who else has access.
- **`maintainer`** adds project membership/settings administration on top of write.

Agent execution **inherits the caller's scope** — a Run a user triggers carries that user's identity
for attribution (but not their session token).

## Where the auth service lives

Authentication and RBAC are a **library inside the apiserver**, not a separate deployment. It owns the
user store, session management, token issuance, and the deny-by-default RBAC middleware. Colocating it
with the apiserver (where the middleware has to sit anyway) avoids a second signing key and a network
hop on every request.

Users and memberships are **durable app state in the same Postgres** (an `auth` schema alongside the
coordination and knowledge records) — not CRDs, because they're high-churn.

## First-run admin bootstrap

KSquad ships **no baked-in default credential** (shipped default passwords are the archetypal
broken-access finding). Instead:

1. On install, Helm generates a **random initial admin password** into a release-scoped Secret
   (`ksquad-bootstrap-admin`) and prints its retrieval command in `NOTES.txt`.
2. On first startup, the auth service runs an **idempotent seed**: *only if* there are zero users, it
   creates a single `admin` user whose password is that generated value, flagged
   **`must_change_password`**.
3. You retrieve the password, log in once, and are **forced to rotate** before any other action.

```bash
kubectl -n ksquad-system get secret ksquad-bootstrap-admin \
  -o jsonpath='{.data.password}' | base64 -d; echo
```

The install-time value is therefore never a durable credential, and re-running the seed on a populated
store is a no-op. This is **fully offline** — no external IdP, no network callback — so it doesn't
break an air-gapped install.

## Managing users and access

As an `admin`, from the console **Users & Roles**:

- create/disable users and set their global role (`admin` / `user`);
- assign users to projects with an access level (`viewer` / `contributor` / `maintainer`);
- change or revoke access — which takes effect immediately (see sessions).

## Sessions and revocation

- On login, the apiserver issues a **short-lived signed access token** (default ~1h) plus a
  **long-lived refresh token, rotated on use** (default ~7d).
- **Revocation is real, not cosmetic**: refresh-token records are server-side and **revoked instantly**
  on logout, user-disable, or membership change. A compromised or offboarded user loses access within
  one short access-token TTL.

Tune the TTLs with `auth.session.accessTokenTTL` / `auth.session.refreshTokenTTL`.

## OIDC / SSO

The local username/password store is the default so the fast, offline install always works. An
**`AuthProvider` seam** keeps **OIDC/SSO a drop-in fast-follow**: enable it with `auth.oidc.*` values,
map your IdP groups to global roles and project access levels, and the first user to authenticate with
the configured `admin.bootstrapSubject` claim is promoted to `admin` (the same one-time, empty-store
guard as the local bootstrap). The `≤4h` install never hard-depends on an external IdP; OIDC layers on
top when you're ready.

## Related

- [Credentials](./credentials) — the *agent* credential plane (distinct from human identity).
- [Console Guide](../console-guide) — the Users & Roles and Login screens.
