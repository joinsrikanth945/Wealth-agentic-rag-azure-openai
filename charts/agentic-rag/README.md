# Helm chart: agentic-rag

Installs the Agentic RAG assistant (FastAPI, LangGraph, Azure OpenAI, Pinecone, Tavily) on Kubernetes
with one command. It deploys the same Docker image and the same hardened setup as the Kustomize
manifests in [`k8s/`](../../k8s/README.md), packaged as a Helm chart with settings in values files.

```powershell
helm upgrade --install agentic-rag ./charts/agentic-rag -n agentic-rag -f charts/agentic-rag/values-local.yaml
```

## What's inside

```
charts/agentic-rag/
├── Chart.yaml               chart name, chart version (0.1.0), app version
├── values.yaml              every setting, with defaults
├── values-local.yaml        kind/minikube: local image, 1 pod, monitoring on
├── values-aks.yaml          Azure Kubernetes Service: Docker Hub image, 2-5 pods
├── dashboards/
│   └── agentic-rag.json     Grafana dashboard (a copy of monitoring/grafana/.../agentic-rag.json; CI checks they match)
└── templates/
    ├── _helpers.tpl         names and labels shared by all templates
    ├── configmap.yaml       non-secret settings
    ├── deployment.yaml      the app: probes, resources, non-root, read-only filesystem
    ├── service.yaml         stable address, port 80 -> 8080
    ├── ingress.yaml         web route (optional)
    ├── hpa.yaml             autoscaling on CPU (optional)
    ├── pdb.yaml             keep pods up during maintenance (optional)
    ├── networkpolicy.yaml   in: app port; out: DNS + HTTPS (optional)
    ├── servicemonitor.yaml  tells Prometheus to scrape /metrics (optional)
    ├── grafana-dashboard.yaml  dashboard for the Grafana sidecar (optional)
    ├── NOTES.txt            what Helm prints after an install
    └── tests/test-health.yaml  `helm test`: checks /api/health and /metrics
```

## How a template works

Templates are the Kubernetes files with `{{ placeholders }}` filled in from the values. For example,
in `templates/hpa.yaml`:

```yaml
{{- if .Values.autoscaling.enabled }}
  minReplicas: {{ .Values.autoscaling.minReplicas }}
  maxReplicas: {{ .Values.autoscaling.maxReplicas }}
{{- end }}
```

With `values-local.yaml` (`minReplicas: 1`, `maxReplicas: 2`) Helm writes `minReplicas: 1`; with
`--set autoscaling.enabled=false` the whole autoscaler is left out. To see the final files without
installing anything:

```powershell
helm template agentic-rag ./charts/agentic-rag -n agentic-rag -f charts/agentic-rag/values-local.yaml
```

## Main settings

| Value | Default | Meaning |
|---|---|---|
| `replicaCount` | `2` | Pods, when autoscaling is off |
| `image.repository` / `image.tag` | Docker Hub image / app version | Which image to run; CI or you can pass a commit SHA |
| `config.LLM_PROVIDER` | `azure` | `azure` for Azure OpenAI, `openai` for OpenAI |
| `existingSecret` | `agentic-rag-secrets` | Secret with the API keys, created from `.env`; the chart never stores keys |
| `ingress.enabled` / `ingress.host` | `true` / `agentic-rag.example.com` | Web address |
| `autoscaling.enabled`, `minReplicas`, `maxReplicas` | `true`, 2, 5 | HorizontalPodAutoscaler on 70% CPU |
| `podDisruptionBudget.enabled` | `true` | Keep at least one pod during maintenance |
| `networkPolicy.enabled` | `true` | Restrict network traffic |
| `serviceMonitor.enabled` | `false` (`true` in local/aks) | Needs kube-prometheus-stack |
| `grafanaDashboard.enabled` | `false` (`true` in local/aks) | Dashboard ConfigMap in the `monitoring` namespace |
| `resources` | 250m CPU / 512Mi requested, 1Gi limit | Pod sizing |

All settings: `helm show values ./charts/agentic-rag`.

## Install on your local cluster

Prerequisites: the kind cluster, ingress controller and metrics-server from [k8s/README.md](../../k8s/README.md)
steps 1-3, the image built and loaded into kind, and (for monitoring) kube-prometheus-stack.

```powershell
# Namespace with the "restricted" security standard, and the API keys from .env (no quotes in .env)
kubectl create namespace agentic-rag
kubectl label namespace agentic-rag pod-security.kubernetes.io/enforce=restricted
kubectl -n agentic-rag create secret generic agentic-rag-secrets --from-env-file=.env

helm upgrade --install agentic-rag ./charts/agentic-rag -n agentic-rag -f charts/agentic-rag/values-local.yaml --wait
helm test agentic-rag -n agentic-rag --logs
```

Open http://agentic-rag.localtest.me. If the app was installed with Kustomize before, remove that first
(see [Switching from Kustomize](#switching-from-kustomize-to-helm)).

## Everyday Helm commands

```powershell
helm list -n agentic-rag                              # installed releases
helm status agentic-rag -n agentic-rag                # status and the NOTES
helm get values agentic-rag -n agentic-rag            # settings you passed
helm upgrade agentic-rag ./charts/agentic-rag -n agentic-rag --reuse-values --set autoscaling.enabled=false --set replicaCount=3
helm history agentic-rag -n agentic-rag               # every revision
helm rollback agentic-rag 1 -n agentic-rag            # back to revision 1
helm test agentic-rag -n agentic-rag --logs           # health check from inside the cluster
helm uninstall agentic-rag -n agentic-rag             # remove (the Secret and namespace stay)
```

After rebuilding the image (`docker build` + `kind load`), restart the pods:
`kubectl -n agentic-rag rollout restart deployment/agentic-rag`.

## Switching from Kustomize to Helm

Kustomize and Helm create resources with the same names, so only one can own them. To move an
existing Kustomize install to Helm:

```powershell
kubectl delete -k k8s/overlays/local                                      # also removes the namespace and Secret
kubectl delete -f k8s/monitoring/servicemonitor.yaml --ignore-not-found
kubectl -n monitoring delete configmap agentic-rag-dashboard --ignore-not-found
```

then follow [Install on your local cluster](#install-on-your-local-cluster). To go back:
`helm uninstall agentic-rag -n agentic-rag`, then the Kustomize steps in [k8s/README.md](../../k8s/README.md).

## Install on AKS

```bash
kubectl create namespace agentic-rag
kubectl label namespace agentic-rag pod-security.kubernetes.io/enforce=restricted
kubectl -n agentic-rag create secret generic agentic-rag-secrets --from-env-file=.env
helm upgrade --install agentic-rag ./charts/agentic-rag -n agentic-rag \
  -f charts/agentic-rag/values-aks.yaml --set ingress.host=<your-dns-name> --set image.tag=<commit-sha>
```

## Versioning

- `version` in `Chart.yaml` is the chart's own version: bump it (0.1.0 → 0.2.0) whenever anything in
  this folder changes.
- `appVersion` is the app version shown in labels; the image tag defaults to it unless `image.tag` is set.

## CI

`.github/workflows/kubernetes.yml` runs `helm lint --strict` with each values file, validates the
rendered output with kubeconform, checks the dashboard copy matches, then installs the chart on a
throwaway kind cluster, runs `helm test`, upgrades, rolls back and tests again.
