# Kubernetes on your laptop with kind. Needs: Docker, kind, kubectl, helm.
#   make k8s-up          create the cluster + ingress + metrics-server
#   make k8s-secrets     load your API keys from .env into the cluster
#   make k8s-deploy      build the image, load it into kind, deploy the app
#   make k8s-monitoring  Prometheus + Grafana in the cluster, with the app dashboard
#   make k8s-grafana     open Grafana on http://localhost:3001
#   make k8s-down        delete the cluster
# See k8s/README.md for the full walkthrough and the Windows (PowerShell) equivalents.

CLUSTER   ?= agentic-rag
NAMESPACE ?= agentic-rag
IMAGE     ?= agentic-rag:local
INGRESS_NGINX_VERSION ?= controller-v1.13.3

.PHONY: k8s-up k8s-secrets k8s-deploy k8s-status k8s-monitoring k8s-grafana k8s-prometheus k8s-down

k8s-up:
	kind create cluster --name $(CLUSTER) --config k8s/kind-config.yaml
	kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/$(INGRESS_NGINX_VERSION)/deploy/static/provider/kind/deploy.yaml
	kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
	kubectl -n kube-system patch deployment metrics-server --type=json \
	  -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
	kubectl -n ingress-nginx wait --for=condition=Ready pod -l app.kubernetes.io/component=controller --timeout=180s

k8s-secrets:
	kubectl create namespace $(NAMESPACE) --dry-run=client -o yaml | kubectl apply -f -
	kubectl -n $(NAMESPACE) create secret generic agentic-rag-secrets --from-env-file=.env \
	  --dry-run=client -o yaml | kubectl apply -f -

k8s-deploy:
	docker build -t $(IMAGE) .
	kind load docker-image $(IMAGE) --name $(CLUSTER)
	kubectl apply -k k8s/overlays/local
	kubectl -n $(NAMESPACE) rollout restart deployment/agentic-rag
	kubectl -n $(NAMESPACE) rollout status deployment/agentic-rag --timeout=180s
	@echo "App: http://agentic-rag.localtest.me"

k8s-status:
	kubectl -n $(NAMESPACE) get pods,svc,ingress,hpa,pdb

k8s-monitoring:
	helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
	helm repo update
	helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
	  -n monitoring --create-namespace -f k8s/monitoring/kube-prometheus-stack-values.yaml --wait
	kubectl apply -f k8s/monitoring/servicemonitor.yaml
	kubectl -n monitoring create configmap agentic-rag-dashboard \
	  --from-file=agentic-rag.json=monitoring/grafana/provisioning/dashboards/agentic-rag.json \
	  --dry-run=client -o yaml | kubectl label --local -f - grafana_dashboard=1 -o yaml | kubectl apply -f -

k8s-grafana:
	@echo "Grafana: http://localhost:3001 (admin / change-me)"
	kubectl -n monitoring port-forward svc/monitoring-grafana 3001:80

k8s-prometheus:
	@echo "Prometheus: http://localhost:9091 (Status > Targets)"
	kubectl -n monitoring port-forward svc/monitoring-kube-prometheus-prometheus 9091:9090

k8s-down:
	kind delete cluster --name $(CLUSTER)
