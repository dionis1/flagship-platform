# Verification record — 18 October 2026

This record distinguishes local execution from cluster-dependent acceptance checks. The screenshot gallery predates these changes.

## End-to-end delivery — passed

After the credentials were restored and the live integration fixes were applied, **Jenkins build #6 succeeded end to end**:

- Source revision: `0fe3443c80372dedbfc2d43160af73f716e8faf2`.
- All **43 regression tests** passed without skips; all 12 manifests passed strict validation.
- The candidate was published to GHCR, scanned with **zero HIGH/CRITICAL findings**, and passed its real Kubernetes HTTP test.
- Git promotion created deployment commit `3bcfa13c0f31197600f9183f3e21eebb2c31b752`.
- Argo CD automatically reconciled that exact commit and became Synced/Healthy. The expected image digest, complete rollout, ready pod, and HTTP response through the Service were verified before Jenkins reported success.
- A manually queued second run remained blocked while build #6 was active. It then ran as **build #7**, classified the generated deployment commit as `skip`, and finished successfully without another image build or Git promotion.

The [evidence summary](evidence/latest-delivery.json) was assembled from Jenkins' archived build metadata, Trivy report, HTTP test results, deployment result, test output, and build/queue API responses. Full build artifacts remain in the local [Jenkins build #6](http://localhost:8080/job/flagship-platform-ci/6/). Local links require this PC's lab to be running.

GitHub webhook delivery remains disabled and needs its own integration checks before enabling it. Mixed-change filtering and competing external Git updates were tested with temporary repositories in the regression suite. Datadog is intentionally disabled at the user's request. The earlier records below document the failures and fixes encountered before this successful run.

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

The subsequent full-path run reached the separate delivery pod and revealed that Git configuration was attempted before installing Git in that fresh Alpine container. Tool bootstrap now runs before Git configuration in both validation/delivery pods. These live-run fixes are distinct from the earlier syntax and unit checks.

### Earlier credential-blocked Jenkins result

[Local build #4](http://localhost:8080/job/flagship-platform-ci/4/) checked out `d7a33c1`, selected the **build** path, provisioned both agent pods, installed the checksum-verified toolchain, validated all 12 resources, and passed **all 39 tests without skips** in the delivery agent. It then failed at the credential binding for candidate publication:

```text
Could not find credentials entry with ID 'ghcr-creds'
```

No new candidate was published or promoted in that run. At that point `github-push` and the Datadog key were also not restored. Those external secrets were a remaining prerequisite; they can be entered locally using `local/configure-credentials.py` or the Jenkins UI.

The live verifier was additionally tested against a deliberately wrong revision on the real Healthy application: it failed as intended and removed the previous success record. Verification of the correct revision then succeeded. Argo CD subsequently synchronized the pushed runtime fixes and continued reporting Healthy.

The committed local Jenkins Dockerfile was also rebuilt successfully under a 512 MiB build limit. It downloads all 66 pinned plugin archives directly and verifies their recorded SHA-256 checksums, avoiding the plugin manager's large metadata memory requirement. At idle, the rebuilt k3s node used approximately 2.1 GiB and the host retained approximately 3.1 GiB available RAM.

### Credentialed live retry

After restoring both Jenkins credential IDs, build #5 published a candidate to GHCR and passed Trivy scanning, but the image HTTP gate failed before promotion because kubectl inside the agent had no kubeconfig. The verifier now creates a temporary mode-0600 in-cluster context referencing the projected CA and `tokenFile` (without copying the token). Explicit local kubeconfigs remain unchanged.

All **43 regression tests** pass with this change. A real pod with the `flagship-ci` ServiceAccount and no host kubeconfig successfully verified the Argo CD revision and Service HTTP response, confirming projected credentials work. Datadog is intentionally left off at the user's request.
