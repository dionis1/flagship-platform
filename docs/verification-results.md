# Verification record — 18 October 2026

This record distinguishes local execution from cluster-dependent acceptance checks. The screenshot gallery predates these changes.

## Executed successfully

- **39 Python regression tests**, including real loopback HTTP requests, temporary Git repositories, image-only/documentation/mixed change filtering, spoofed skip messages, missing build history, stale promotion rejection, a competing deployment, a non-fast-forward Git push race, rollout-state checks, Service HTTP failure, first-sync delay, and a newer revision appearing during verification.
- **Strict schema validation**: 11 Kubernetes/RBAC resources and one Argo CD Application, with zero invalid, skipped, or errored resources. Negative tests demonstrate rejection of an invalid port type and an unknown Deployment field.
- **Real Jenkins Declarative Pipeline validation** using an isolated Jenkins 2.580.1 instance with the required pipeline plugins: `Jenkinsfile successfully validated.` The temporary instance was removed after testing; this did not execute a delivery job or use existing Jenkins credentials.
- **Actual application image build and HTTP test**: the built NGINX container returned HTTP 200 and the expected project heading. The test container was stopped afterward.
- **Trivy v0.76.0 image scan** with the configured HIGH/CRITICAL policy: the original image failed on four HIGH findings. Updating NGINX to 1.30.6 and pinning patched `libexpat=2.9.0-r0` produced **zero HIGH/CRITICAL findings** at scan time. The final image was checked again over HTTP. This is not a claim that lower-severity findings are absent or that future database updates will continue to pass.
- The exact CI tool bootstrap and then-current 38-test validation suite also passed in a temporary Alpine 3.20 container matching the Jenkins tools agent.
- Agent YAML parsing, Python compilation, shell syntax checks, and Git whitespace checks.

## Initial limitations (before the live rebuild below)

The local k3s service was inactive and its executable was unavailable during this work. At that point no full Jenkins → GHCR → Argo CD delivery run was performed. Deployment orchestration and failure handling were tested with simulated Kubernetes responses; the actual image was executed locally in Docker.

Before enabling automatic delivery:

1. Bring up the intended cluster and verify its Kubernetes/Argo CD versions against the configured schema targets.
2. Apply `ci/verification-rbac.yaml` as an administrator and configure registry pull credentials if the image is private.
3. Audit the actual Jenkins job trust configuration and GitHub credential permissions.
4. Run a manual full delivery job and retain its scan, image-test, deployment-revision, and HTTP verification artifacts.
5. Complete the webhook/trigger acceptance checks in [the CI operating guide](ci-verification.md#trigger-policy-and-acceptance-checks).

No production environment, branch protection, token permission, or webhook setting was changed by this implementation. Direct development promotion and privileged BuildKit remain explicit lab tradeoffs.

## Live rebuild follow-up

A subsequent retry rebuilt the lab as k3s v1.31.14 inside k3d, with a 4.5 GiB node limit, Jenkins 2.580.1, and Argo CD v3.5.5. See `local/README.md` for local endpoints, startup/shutdown, and private state handling.

- Argo CD synchronized revision `3a6a949d290123ffb07296a72544981a1f774544` and reported the demo application Synced/Healthy.
- The rebuilt candidate image passed the real Kubernetes temporary-pod HTTP test under the restricted `flagship-ci` identity.
- The deployment verifier passed against the real Argo CD Application, Deployment, ready pod, and Service HTTP endpoint under that same identity. This checked the previously published image tag `16-379f6ff`; it does not prove publication/promotion of a new candidate digest.
- Actual authorization checks confirmed the CI identity cannot read Secrets, patch Deployments, or list all Deployments without a name selector.
- The live rollout test exposed a missing named-Deployment `list` permission needed by `kubectl rollout status`; the Role now grants that verb only for `demo-app`. Errors from kubectl are retained in diagnostics, and reruns remove stale success records.
- The first real Jenkins build exposed a checkout integration issue: SCM values must be read from the map returned by `checkout(scm)` in this agent-none job. The branch/history logic now uses that map. The corrected Jenkinsfile passed the rebuilt Jenkins validator and all 39 regression tests.

External GHCR/GitHub deployment credentials and the Datadog API key were absent from the saved configuration. Full new-image Jenkins delivery and Datadog monitoring still require those credentials. Automatic build triggers remain disabled pending the documented acceptance checks.

The next live Jenkins run also exposed a Declarative environment precedence issue: a fixed top-level `PIPELINE_ACTION=skip` overrode the dynamically classified action. That fixed declaration was removed so the classifier can select the delivery stages. A successful skipped job must not be confused with a successful full delivery.
