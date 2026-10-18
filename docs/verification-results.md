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

## Still required in the running lab

The local k3s service was inactive and its executable was unavailable during this work. No full Jenkins → GHCR → Argo CD delivery run was performed. Deployment orchestration and failure handling were tested with simulated Kubernetes responses; the actual image was executed locally in Docker.

Before enabling automatic delivery:

1. Bring up the intended cluster and verify its Kubernetes/Argo CD versions against the configured schema targets.
2. Apply `ci/verification-rbac.yaml` as an administrator and configure registry pull credentials if the image is private.
3. Audit the actual Jenkins job trust configuration and GitHub credential permissions.
4. Run a manual full delivery job and retain its scan, image-test, deployment-revision, and HTTP verification artifacts.
5. Complete the webhook/trigger acceptance checks in [the CI operating guide](ci-verification.md#trigger-policy-and-acceptance-checks).

No production environment, branch protection, token permission, or webhook setting was changed by this implementation. Direct development promotion and privileged BuildKit remain explicit lab tradeoffs.
