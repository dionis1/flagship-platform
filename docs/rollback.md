# GitOps rollback demonstration

This is a portfolio exercise on a local lab, not a recovery plan for a real development or production service.

## Verified on 18 October 2026

The lab started from Git revision `e3a18a55fd8d135431e1cb715ba1787573cba44a` with the image from successful Jenkins build #6. A temporary image-only Git change selected a different previously published image whose archived build #5 Trivy report contained zero HIGH/CRITICAL findings. A normal `git revert` then restored the original digest. Both images serve the same static page: this tests image restoration through GitOps, not an injected application outage.

| Step | Git revision | Image digest suffix | Result |
| --- | --- | --- | --- |
| Demonstration image | `708be25c65fd91cd12573e2d4e6b73ce8980a917` | `23db65a6…bdd44c51` | Exact Argo revision, expected image, healthy rollout, and Service HTTP check passed |
| Git revert / restored image | `53fb75789a7a6ea79d384ed7fa82b605bef10e39` | `fd714f87…8fb1033` | Exact Argo revision, expected image, healthy rollout, and Service HTTP check passed |

The [JSON evidence](evidence/rollback.json) records full digests and verification results. The [gallery](screenshots/README.md) shows Healthy/Synced before and after the revert and the restored web page. An administrator requested an Argo CD hard refresh after each push to shorten the wait. Argo CD applied both changes automatically; no Deployment was edited directly. Jenkins was not rebuilt for these image-only commits. Datadog stayed off, and the cluster was stopped after the captures to release RAM.

## Repeat in the portfolio lab

Use a clean checkout, trusted credentials, and a known available, scanned image. Confirm the deployment change being reverted is image-only and that nobody has promoted a newer image. Resolve any competing promotion before continuing.

```bash
git switch main
git pull --ff-only
# Inspect the selected promotion commit and its parent image first.
git show <deployment-commit> -- kubernetes/dev/demo-app/deployment.yaml
git revert <deployment-commit>
git show --stat HEAD
git push origin main
```

Do not force-push. If the push is rejected, fetch and inspect the intervening changes before deciding whether the rollback is still appropriate. A revert creates a new desired-state commit; the expected Argo revision is that new commit, not the old revision it restores.

From the repository root, use the local administrator context for this manual lab exercise:

```bash
. local/env.sh
python3 ci/kube_checks.py deployment \
  --revision "$(git rev-parse HEAD)" \
  --image 'ghcr.io/dionis1/flagship-demo-app@sha256:<restored-digest>' \
  --timeout 180
```

The verifier checks the exact reconciled revision, expected deployed image, ready rollout, and HTTP 200 with expected content through the Service. Its reports are written under `reports/`. A previous Healthy status alone is insufficient. Argo CD can reconcile by its normal polling; a manual refresh requests an earlier repository check and does not replace verification.

Avoid `kubectl rollout undo` in this GitOps workflow: it changes the live workload without changing desired state, so Argo CD self-healing can overwrite it. Keep the rollback in Git.

## Limits

This exercise does not establish database rollback, backup restoration, disaster recovery, high availability, or behavior under a real application failure. It does not remove the privileged-builder or automatic-promotion risks described in the [README](../README.md#security-limitations-and-intended-use). No new vulnerability scan was run during the rollback; it used the previously archived image scans.
