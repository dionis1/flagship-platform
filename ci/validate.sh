#!/bin/sh
set -eu
mkdir -p reports
# Match the existing lab's declared Kubernetes API target; override only when
# deliberately upgrading the cluster and its schema validation together.
kubeconform -strict -summary -kubernetes-version "${KUBERNETES_VERSION:-1.31.0}" \
  kubernetes/dev/namespace.yaml kubernetes/dev/demo-app/ ci/verification-rbac.yaml > reports/kubeconform.txt
cat reports/kubeconform.txt
# Argo CD Application schema is pinned to the documented CRD version.
kubeconform -strict -summary -schema-location 'ci/schemas/{{ .ResourceKind }}_{{ .ResourceAPIVersion }}.json' \
  argocd/dev-demo-app.yaml > reports/argocd-schema.txt
cat reports/argocd-schema.txt
python3 -m unittest discover -s tests -v > reports/tests.txt 2>&1 || { cat reports/tests.txt; exit 1; }
cat reports/tests.txt
