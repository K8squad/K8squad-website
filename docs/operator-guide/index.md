---
title: Operator Guide
description: Install, configure, secure, and run KSquad for a team — install and exposure, configuration, credentials, RBAC, and settings.
sidebar_position: 3
---

# Operator Guide

This guide is for the **platform engineer** who installs and runs KSquad for a team. It covers the
control plane end to end: installing, wiring networking and storage, managing credentials, granting
human access with RBAC, and tuning runtime settings.

If you just want to try KSquad, start with the [Quickstart](../quickstart). Come back here when you're
ready to run it for real.

## In this guide

| Page | What it covers |
|------|----------------|
| [Install & exposure](./install) | `helm install`, dependencies, networking (Gateway API), storage, air-gapped installs, sandbox runtime |
| [Configuration](./configuration) | Chart values, HA toggles, warm-pool policy, egress defaults, runtime images |
| [Credentials](./credentials) | Connecting Claude, zero-touch refresh, non-Claude keys, BYO model endpoints, rotation |
| [RBAC & access levels](./rbac) | Users, roles, per-project access levels, first-run admin, OIDC seam |
| [Settings](./settings) | Console Settings, `OTelConfig`, plugins, and per-project configuration |

## What you're responsible for

KSquad is designed to be installed by one person in an afternoon, but as the operator you own a few
decisions the chart deliberately **does not guess**:

- **StorageClass** — every PVC takes its class from values; there is no cluster-default fallback.
- **Exposure mode** — `gateway`, `ingress`, or `clusterip`, pre-flighted at install time.
- **Isolation runtime** — gVisor is the recommended default; the fallback is clearly flagged.
- **The first admin password** — generated at install, rotated on first login.

Each of these is covered in the pages above, with the reasoning behind the "no silent default" stance.
