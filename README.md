# OTelConfig CRD

Dedicated CRD for configuring OTLP export endpoints for KSquad telemetry (traces, metrics, logs).

## Design Principles

- **Default = no exporter (opt-in).** Absent an OTelConfig, telemetry stays in-cluster. Nothing egresses. (D8 privacy-safe default)
- **Per-signal routing.** Traces, metrics, and logs each have independent exporter config. Supports fan-out (e.g. traces→Dynatrace, metrics→Prometheus, logs→Loki).
- **Auth credentials are Secret refs, never inline, never logged.** BYO-Secret discipline (§11).
- **Platform-scoped.** Lives in `ksquad-system` namespace. Per-Team override is a possible fast-follow, not v1.

## CRD Schema

```yaml
apiVersion: ksquad.io/v1alpha1
kind: OTelConfig
metadata:
  name: ksquad-otel-export
  namespace: ksquad-system
spec:
  exporters:
    traces:
      endpoint: "https://api.dynatrace.com/api/v2/otlp"
      protocol: grpc          # grpc | http
      authSecretRef:
        name: dt-otel-token
        key: token             # defaults to "token"
      resourceAttributes:
        environment: production
      sampling:
        type: parentbased_traceidratio
        ratio: "0.25"
    metrics:
      endpoint: "http://prometheus-gateway:4318"
      protocol: http
      authSecretRef:
        name: prometheus-auth
    logs:
      endpoint: "http://loki-gateway:4318"
      protocol: grpc
      authSecretRef:
        name: loki-auth
```

## Reconciler Behaviour

1. Watches `OTelConfig` CR in `ksquad-system`.
2. Validates all referenced auth Secrets exist and contain expected keys.
3. Builds a TOML config map (`exporter.toml`) with endpoint/protocol/refs — **no credentials inlined**.
4. Writes to `ksquad-otel-export-config` ConfigMap.
5. All KSquad components (operator, apiserver, memory, console, shims) mount this ConfigMap + projected Secrets.
6. Components read their OTLP exporter settings at runtime.
7. Status conditions: `Ready`, `SecretResolved`, `ExportersApplied`.

## Files

```
api/v1alpha1/
  otelconfig_types.go        # CRD Go types + kubebuilder markers
  groupversion_info.go       # GVK registration
  zz_generated.deepcopy.go   # DeepCopy implementation
internal/controller/
  otelconfig_controller.go   # Reconciler (validate secrets → build config → apply ConfigMap)
config/
  crd/bases/
    ksquad.io_otelconfigs.yaml   # Generated CRD manifest
  rbac/
    role.yaml                    # ClusterRole for the reconciler
  samples/
    otelconfig_simple.yaml       # Traces-only example
    otelconfig_fanout.yaml       # Fan-out example (3 destinations)
```

## Architecture References

- §5.1 CRD surface, §5.2 reconciler design, §17.2 observability pipeline
- ADR-029: OTelConfig CRD for opt-in telemetry export
- Paired console surface: ISI-2288 (Settings page writes this CRD via BFF)
