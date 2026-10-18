# Local rebuild

The rebuilt lab runs a single k3s node inside Docker, managed by k3d v5.9.0. It does not use a host `k3s.service`. Its API and web ports are bound to loopback only:

- Jenkins: http://localhost:8080
- Argo CD: http://localhost:8081
- Kubernetes API: https://127.0.0.1:6445

Source the isolated Kubernetes/Helm environment from the repository root:

```bash
. local/env.sh
kubectl get pods -A
```

Private kubeconfig, binaries, installation logs, and local images live under ignored `.local/`. Do not commit that directory. The cluster uses Kubernetes v1.31.14 to match the current pipeline API target; this is a compatibility lab configuration, not a recommendation for a new production cluster. Plan an explicit upgrade of cluster, kubectl, and schema targets together.

The Jenkins chart is pinned to 5.9.69. Its local image bundles the pipeline, Kubernetes, Git, credential-binding, configuration-as-code, and Job DSL plugins. `local/jenkins-values.yaml` creates a trusted-main, manual-only job named `flagship-platform-ci`. Optional Argo CD Dex, ApplicationSet, and notification controllers are scaled to zero for this lab.

## Rebuild from source

Requires Docker, Python 3 with PyYAML, kubectl, and Helm on Linux AMD64. The bootstrap downloads checksum-pinned k3d, builds Jenkins with the exact recorded plugin versions, verifies the plugin archive checksums, creates or starts the isolated cluster, and installs the pinned charts/manifests:

```bash
./local/bootstrap.sh
```

It never restores external credentials from source control.

## Start and stop without deleting data

```bash
./local/stop.sh    # release cluster RAM, preserve containers and Jenkins volume
./local/start.sh   # resume the lab
```

Do not use cluster deletion to stop the lab. The k3d node has a 4.5 GiB memory limit; run only one delivery build at a time.

## Local UI passwords

Both web UIs use username `admin`. Retrieve passwords in your own terminal:

```bash
. local/env.sh
kubectl -n jenkins get secret jenkins -o jsonpath='{.data.jenkins-admin-password}' | base64 -d; echo
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d; echo
```

Do not paste passwords or tokens into chat. Argo CD serves HTTP only on the loopback-bound local web port; do not expose these ports to your network.

## Restore external credentials

The old cluster's project credentials were not available. Restore the two Jenkins credential IDs using the UI or this interactive helper on your PC:

```bash
python3 local/configure-credentials.py
```

The helper prompts with hidden input and sends tokens only to local Jenkins/the local Kubernetes API. It does not store them in source files. Audit token scopes as described in `docs/ci-verification.md` before entering them. For existing credential IDs, edit them in Jenkins rather than rerunning the create helper.

Datadog installation requires the API key Secret created by the helper. After that:

```bash
. local/env.sh
helm upgrade --install datadog datadog --repo https://helm.datadoghq.com \
  --namespace datadog -f helm/datadog/values.yaml
```

Before enabling webhooks, run the manual Jenkins job and complete the trigger acceptance checks in `docs/ci-verification.md`. Full registry publication and Git promotion require `ghcr-creds` and `github-push`; these cannot be recovered from the repository.
