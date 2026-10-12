# Running the agent on Kubernetes

The same Docker image that runs on Azure Container Apps, deployed to Kubernetes with
security hardening, health probes, autoscaling and in-cluster Prometheus + Grafana.

The live demo still deploys to Azure Container Apps. This folder adds Kubernetes alongside it:
CI deploys the app to a throwaway [kind](https://kind.sigs.k8s.io/) cluster on every push to
prove the manifests work, and you can run the same setup on your own machine for free.

**Status:** verified end to end on a local kind cluster (Windows 11, Docker Desktop): the app
answers questions through Azure OpenAI (`chat/completions` and `embeddings` return 200),
Pinecone and Tavily, and the Grafana dashboard updates from the in-cluster Prometheus.

## Contents

- [What's here](#whats-here)
- [Design choices](#design-choices)
- [Run it on your machine](#run-it-on-your-machine)
- [Monitoring](#monitoring)
- [Day-to-day commands](#day-to-day-commands)
- [Troubleshooting](#troubleshooting)
- [Deploying to AKS later](#deploying-to-aks-later)
- [CI](#ci)

## What's here

```
k8s/
├── base/                       shared by every environment
│   ├── namespace.yaml          namespace with the "restricted" Pod Security Standard
│   ├── configmap.yaml          non-secret settings (provider, writable paths)
│   ├── deployment.yaml         probes, resources, non-root, read-only filesystem
│   ├── service.yaml            ClusterIP on port 80 -> 8080
│   ├── ingress.yaml            ingress-nginx, larger uploads, longer timeouts
│   ├── hpa.yaml                2-5 pods on CPU
│   ├── pdb.yaml                keeps one pod up during node maintenance
│   ├── networkpolicy.yaml      in: HTTP only; out: DNS + HTTPS only
│   └── kustomization.yaml      lists the files above
├── overlays/
│   ├── local/                  kind/minikube: local image, 1 pod, agentic-rag.localtest.me
│   └── aks/                    Azure Kubernetes Service: Docker Hub image, 2-5 pods
├── monitoring/
│   ├── kube-prometheus-stack-values.yaml   Prometheus + Grafana via Helm
│   └── servicemonitor.yaml                 tells Prometheus to scrape the app's /metrics
└── kind-config.yaml            local cluster with ports 80/443 mapped to your machine
```

```mermaid
flowchart LR
    U([Browser]) --> I[Ingress<br/>ingress-nginx]
    I --> S[Service<br/>agentic-rag:80]
    S --> P1[Pod]
    S --> P2[Pod]
    H[HPA] -. scales .-> P1
    PR[Prometheus] -- ServiceMonitor<br/>/metrics --> S
    G[Grafana] --> PR
    P1 & P2 -- HTTPS --> X[(Azure OpenAI<br/>Pinecone · Tavily)]
```

**Kustomize:** `base/` holds everything shared; each overlay changes only what differs per
environment (image, host name, number of pods). `kubectl apply -k k8s/overlays/local` merges
them and applies the result.

## Design choices

| Concern | How it's handled |
|---|---|
| Secrets | API keys are a Kubernetes Secret built from your local `.env`; nothing secret is committed. On AKS, the next step is Azure Key Vault with the Secrets Store CSI driver. |
| Security | Runs as UID 10001, read-only root filesystem, all Linux capabilities dropped, no privilege escalation, no service-account token, namespace enforces the `restricted` Pod Security Standard. |
| Writable storage | The SQLite audit log and uploads go to a per-pod volume at `/var/lib/agentic-rag` (set through `AUDIT_DB_PATH` and `UPLOAD_DIR`). Each pod has its own audit log, reset when the pod is replaced; a managed database would make it shared and durable. The knowledge base lives in Pinecone, so pods are otherwise stateless. |
| Availability | Rolling updates with `maxUnavailable: 0`, readiness/liveness/startup probes on `/api/health` (the startup probe allows up to 2 minutes for LangChain to load), pods spread across nodes, PodDisruptionBudget. |
| Scaling | HorizontalPodAutoscaler on CPU (needs metrics-server). |
| Observability | `kube-prometheus-stack` via Helm; a ServiceMonitor scrapes `/metrics` every 15 s; the existing Grafana dashboard (`monitoring/grafana/.../agentic-rag.json`) is loaded unchanged. |

## Run it on your machine

You need [Docker Desktop](https://www.docker.com/products/docker-desktop/) running, plus
`kind`, `kubectl` and `helm`. Commands below are PowerShell, run from the repository folder.
On macOS, Linux or WSL you can use the `make` targets instead (see the [Makefile](../Makefile)).

### 1. Install the tools

`kubectl` comes with Docker Desktop. For `kind` and `helm`, either use winget:

```powershell
winget install Kubernetes.kind Helm.Helm
```

or, if winget isn't available, download them into `$HOME\bin`:

```powershell
mkdir $HOME\bin -Force
curl.exe -Lo $HOME\bin\kind.exe https://kind.sigs.k8s.io/dl/latest/kind-windows-amd64
curl.exe -Lo $HOME\helm.zip https://get.helm.sh/helm-v3.19.0-windows-amd64.zip
Expand-Archive -Path $HOME\helm.zip -DestinationPath $HOME\helm-tmp -Force
Copy-Item $HOME\helm-tmp\windows-amd64\helm.exe $HOME\bin\helm.exe
Remove-Item $HOME\helm.zip, $HOME\helm-tmp -Recurse -Force

# make $HOME\bin available now and in new windows
$env:Path += ";$HOME\bin"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
[Environment]::SetEnvironmentVariable("Path", "$userPath;$HOME\bin", "User")

kind version; helm version; kubectl version --client
```

### 2. Create the cluster

```powershell
kind create cluster --name agentic-rag --config k8s/kind-config.yaml
kubectl config current-context        # should print: kind-agentic-rag
```

### 3. Ingress controller and metrics-server

```powershell
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.13.3/deploy/static/provider/kind/deploy.yaml
kubectl -n ingress-nginx wait --for=condition=Ready pod -l app.kubernetes.io/component=controller --timeout=180s

kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
kubectl -n kube-system patch deployment metrics-server --type=json -p '[{\"op\":\"add\",\"path\":\"/spec/template/spec/containers/0/args/-\",\"value\":\"--kubelet-insecure-tls\"}]'
```

### 4. API keys

The Secret is created from `.env`. **Write the values without quotes**: Kubernetes keeps quotes
as part of the value (docker compose strips them), which breaks API keys. To remove quotes from
an existing `.env` (a backup is kept; don't commit it):

```powershell
Copy-Item .env .env.backup
$lines = (Get-Content .env) -replace '^([^#=]+)="(.*)"$', '$1=$2' -replace "^([^#=]+)='(.*)'$", '$1=$2'
[IO.File]::WriteAllLines("$PWD\.env", $lines)
```

For Azure OpenAI, `.env` needs `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `PINECONE_API_KEY`,
`TAVILY_API_KEY` and `ADMIN_API_KEY` (the ConfigMap already sets `LLM_PROVIDER=azure`). Then:

```powershell
kubectl create namespace agentic-rag
kubectl -n agentic-rag create secret generic agentic-rag-secrets --from-env-file=.env
```

### 5. Build and deploy

```powershell
docker build -t agentic-rag:local .
kind load docker-image agentic-rag:local --name agentic-rag
kubectl apply -k k8s/overlays/local
kubectl -n agentic-rag rollout status deployment/agentic-rag --timeout=240s
kubectl -n agentic-rag get pods          # 1/1 Running
```

### 6. Open the app

`agentic-rag.localtest.me` is a public DNS name that points to `127.0.0.1`. Some routers and
providers don't resolve it; if the browser says "site can't be reached", add it to the Windows
hosts file (opens an administrator window; click **Yes**):

```powershell
Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -Command "Add-Content -Path C:\Windows\System32\drivers\etc\hosts -Value \"`r`n127.0.0.1 agentic-rag.localtest.me\"; ipconfig /flushdns"'
```

Then open **http://agentic-rag.localtest.me**. Without changing the hosts file you can use
`kubectl -n agentic-rag port-forward svc/agentic-rag 8081:80` and open http://localhost:8081.

Check it from the command line:

```powershell
curl.exe http://agentic-rag.localtest.me/api/health
```

## Monitoring

Installs Prometheus, Grafana, Alertmanager, kube-state-metrics and node-exporter with Helm,
then points Prometheus at the app and loads the existing dashboard.

```powershell
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack `
  -n monitoring --create-namespace `
  -f k8s/monitoring/kube-prometheus-stack-values.yaml --wait --timeout 10m

kubectl apply -f k8s/monitoring/servicemonitor.yaml
kubectl -n monitoring create configmap agentic-rag-dashboard `
  --from-file=agentic-rag.json=monitoring/grafana/provisioning/dashboards/agentic-rag.json
kubectl -n monitoring label configmap agentic-rag-dashboard grafana_dashboard=1
```

| Piece | What it does |
|---|---|
| `kube-prometheus-stack` (Helm chart) | Prometheus, Grafana, Alertmanager, the Prometheus Operator, kube-state-metrics and node-exporter |
| `kube-prometheus-stack-values.yaml` | Lets Prometheus use ServiceMonitors from every namespace; Grafana loads ConfigMaps labelled `grafana_dashboard` as dashboards; data-source uid `prometheus` to match the dashboard; small resource requests for a laptop |
| `servicemonitor.yaml` | "Scrape the `http` port of the Service labelled `agentic-rag`, path `/metrics`, every 15 s" |
| Dashboard ConfigMap | The same dashboard file used by docker compose, picked up automatically |

**Open Grafana** in its own PowerShell window and leave it running (port 3001, so it doesn't
clash with the docker compose Grafana on 3000):

```powershell
kubectl -n monitoring port-forward svc/monitoring-grafana 3001:80
```

Go to **http://localhost:3001** (`admin` / `change-me`), **Dashboards → Agentic RAG - Overview**,
time range **Last 15 minutes**.

**Send some questions** to see the panels move (new data appears after 30-60 seconds):

```powershell
$questions = @(
  "How long is a client's digital activation link valid?",
  "What happens when an order fails the suitability check?",
  "How do I register a LumenKey token for a new user?",
  "What should I do if a user loses the phone with their token?",
  "How long does an account closure take?"
)
foreach ($q in $questions) {
  $body = @{ question = $q } | ConvertTo-Json
  $r = Invoke-RestMethod -Uri http://agentic-rag.localtest.me/api/chat -Method Post -Body $body -ContentType "application/json"
  Write-Host "$q  ->  $($r.source_used)"
}
```

**Check Prometheus is scraping the app:**

```powershell
kubectl -n monitoring port-forward svc/monitoring-kube-prometheus-prometheus 9091:9090
```

Open http://localhost:9091, **Status → Targets**: the `agentic-rag` target should be **UP**.

> **Two Grafanas.** docker compose has its own Prometheus + Grafana (ports 9090/3000) that watch
> the docker compose app on `localhost:8080` and the Azure app. Questions asked at
> `agentic-rag.localtest.me` only show on the Kubernetes Grafana (`localhost:3001`). In Grafana,
> **Connections → Data sources → Prometheus** tells them apart: `http://prometheus:9090` is docker
> compose; `http://monitoring-kube-prometheus-prometheus.monitoring:9090` is Kubernetes.

## Day-to-day commands

```powershell
kubectl -n agentic-rag get pods,svc,ingress,hpa,pdb          # what's running
kubectl -n agentic-rag logs -f deployment/agentic-rag        # live logs
kubectl -n agentic-rag describe pod <pod-name>               # why a pod is unhappy
kubectl -n agentic-rag delete pod -l app.kubernetes.io/component=api   # self-healing demo
kubectl -n agentic-rag scale deployment/agentic-rag --replicas=3       # scaling demo
kubectl -n agentic-rag get hpa                               # autoscaler status
helm list -A                                                 # Helm releases
```

After editing `.env`:

```powershell
kubectl -n agentic-rag create secret generic agentic-rag-secrets --from-env-file=.env --dry-run=client -o yaml | kubectl apply -f -
kubectl -n agentic-rag rollout restart deployment/agentic-rag
```

After changing the code:

```powershell
docker build -t agentic-rag:local .
kind load docker-image agentic-rag:local --name agentic-rag
kubectl -n agentic-rag rollout restart deployment/agentic-rag
```

Free the memory when you're done (`docker compose stop` also helps if that stack is running):

```powershell
kind delete cluster --name agentic-rag
```

kind's default network plugin doesn't enforce NetworkPolicies; AKS with Azure CNI or Calico does.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `kubectl get pods`: "the server could not find the requested resource" | No cluster yet (`kubectl config current-context` says "not set"), so kubectl falls back to `localhost:8080`, which is the docker compose app | Create the cluster (step 2) |
| `kind` / `winget` "is not recognized" | Tool not installed, or the window was opened before installing | Use the download method in step 1, or reopen PowerShell |
| Browser: "site can't be reached" for `agentic-rag.localtest.me`, but `curl.exe -H "Host: agentic-rag.localtest.me" http://localhost/api/health` works | Your network doesn't resolve `localtest.me` | Add it to the hosts file (step 6) or use port-forward |
| Health check shows the app name with extra quotes; LLM calls fail with 401 | Quotes in `.env` values are kept by Kubernetes | Remove the quotes, re-create the Secret, restart the deployment |
| Dashboard doesn't change after questions | Watching the docker compose Grafana (`localhost:3000`) | Use the Kubernetes Grafana on `localhost:3001` |
| `localhost:3001` doesn't open | The port-forward isn't running | Run the port-forward in its own window and leave it open |
| Pod stuck in `ImagePullBackOff` | The image wasn't loaded into kind | `kind load docker-image agentic-rag:local --name agentic-rag` |
| Pod in `CrashLoopBackOff` | The app fails at start-up | `kubectl -n agentic-rag logs deployment/agentic-rag --previous` |
| `kind create cluster` fails on port 80 | Another program (IIS, Skype, a web server) uses port 80 | Stop it, or change `hostPort` in `kind-config.yaml` (e.g. 8088) and browse to `:8088` |

## Deploying to AKS later

The `aks` overlay is ready but not wired to CI, so nothing is created or billed until you choose to.
Roughly $50-60/month for one small node on the Free tier; `az aks stop` when idle.

```bash
az aks create -g agentic-rag-rg -n agentic-rag-aks --tier free \
  --node-count 1 --node-vm-size Standard_B2s --network-policy azure --generate-ssh-keys
az aks get-credentials -g agentic-rag-rg -n agentic-rag-aks
helm upgrade --install ingress-nginx ingress-nginx --repo https://kubernetes.github.io/ingress-nginx \
  -n ingress-nginx --create-namespace
kubectl create namespace agentic-rag
kubectl -n agentic-rag create secret generic agentic-rag-secrets --from-env-file=.env
# set your host in k8s/overlays/aks/kustomization.yaml, then:
kubectl apply -k k8s/overlays/aks

az aks stop  -g agentic-rag-rg -n agentic-rag-aks   # stop paying for nodes when idle
az aks start -g agentic-rag-rg -n agentic-rag-aks
```

## CI

The `kubernetes` job in `.github/workflows/tests.yml` runs on every push and pull request:

1. Renders both overlays with Kustomize and validates them with kubeconform.
2. Creates a kind cluster on the runner, builds the image and deploys the `local` overlay.
3. Waits for the rollout and checks `/api/health` and `/metrics` through the Service.
4. On failure, prints pod status, events and logs.

It runs alongside the Azure Container Apps pipeline and doesn't block the deployment.
