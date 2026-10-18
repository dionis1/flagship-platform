#!/bin/sh
# Requires Docker, Python 3 + PyYAML, kubectl, and Helm on the host.
set -eu
umask 077
cd "$(dirname "$0")/.."
mkdir -p .local/bin .local/helm
chmod 700 .local
if [ ! -x .local/bin/k3d ]; then
    python3 - <<'PY'
import hashlib, urllib.request
from pathlib import Path
url='https://github.com/k3d-io/k3d/releases/download/v5.9.0/k3d-linux-amd64'
with urllib.request.urlopen(url,timeout=120) as r: data=r.read()
assert hashlib.sha256(data).hexdigest() == '06d8f25bc3a971c4eb29e0ff08429b180402db0f4dec838c9eac427e296800a0'
p=Path('.local/bin/k3d');p.write_bytes(data);p.chmod(0o755)
PY
fi
docker build -f local/Dockerfile.jenkins -t flagship-jenkins:local local
if docker inspect k3d-flagship-platform-server-0 >/dev/null 2>&1; then
    .local/bin/k3d cluster start flagship-platform
else
    .local/bin/k3d cluster create --config local/k3d.yaml --servers-memory 4608m
fi
.local/bin/k3d kubeconfig get flagship-platform > .local/kubeconfig
chmod 600 .local/kubeconfig
. ./local/env.sh
for namespace in jenkins argocd dev; do
    kubectl create namespace "$namespace" --dry-run=client -o yaml | kubectl apply -f -
done
kubectl apply -f ci/verification-rbac.yaml
.local/bin/k3d image import flagship-jenkins:local --cluster flagship-platform
helm upgrade --install jenkins jenkins --repo https://charts.jenkins.io --version 5.9.69 \
    --namespace jenkins -f helm/jenkins/values.yaml -f local/jenkins-values.yaml --wait --timeout 8m
python3 local/prepare-argocd.py
kubectl apply --server-side -n argocd -f .local/argocd-install.yaml
kubectl -n argocd rollout status deployment/argocd-server --timeout=300s
kubectl apply -f local/argocd-project.yaml
kubectl apply -f argocd/dev-demo-app.yaml
printf '\nLab ready. See local/README.md for passwords and credential restoration.\n'
