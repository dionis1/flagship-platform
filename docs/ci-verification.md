# CI gates, deployment verification, and operating instructions

## Pipeline contract

Only a trusted `main` delivery job may run this pipeline. It does not accept pull-request jobs or other branches. Configure Jenkins to retrieve the Jenkinsfile from `main`; do not let a fork or PR replace this Jenkinsfile in a credentialed job. Runtime branch checks are defense in depth, not a sandbox for an untrusted Jenkinsfile. Use a separate credential-free job and unprivileged agents if adding PR validation.

The flow is:

1. Check out the source in a lightweight pod without a Kubernetes API token or privileged container.
2. Classify all changes since the previous successful build. If the base is absent, unavailable, or divergent, build conservatively, except for a provably image-only latest commit (which must still skip to prevent loops).
3. For applicable changes, run strict Kubernetes 1.31.0 schema validation, pinned Argo CD Application schema validation, and the test suite.
4. Build and publish a **candidate** image. Record its registry digest from BuildKit metadata.
5. Scan that exact digest with Trivy v0.76.0. **Any HIGH or CRITICAL vulnerability blocks promotion**, including unfixed findings. Scanner/database/network errors also fail the build. Archive the JSON result. No vulnerability ignore list is used.
6. Run the same digest in a short-lived Kubernetes pod and require HTTP 200 plus `<h1>DevOps Flagship Platform</h1>`. Delete the pod on success or failure. It has no service account token and a 150-second lifetime limit.
7. Fetch current `main` in a separate checkout and promote the tested digest. Reject newer application/CI/manifests or a competing deployment. Preserve intervening documentation changes. Retry at most three times on non-fast-forward push races; never force-push. If the tested digest is already deployed, reuse the current Git revision instead of creating an empty commit.
8. Wait up to six minutes for the **exact deployment commit**, Synced and Healthy Argo CD status, the expected Deployment image digest, observed generation, complete rollout, and ready pods on that digest. Check HTTP through the application Service, then recheck the revision and image to catch a racing deployment. An eight-minute Jenkins stage timeout bounds diagnostics and HTTP verification too.

A candidate may exist in GHCR after a failed scan or test. Publication is not deployment approval; the manifest changes only after the image passes both gates. Clean up unused candidate images with a registry retention policy if needed. A failed deployment verification does not automatically roll Git back: inspect the archived diagnostics and revert the deployment commit through your normal Git workflow.

The existing screenshot gallery shows the previous pipeline. It is historical evidence, not evidence that these new stages have run in Jenkins.

## One-time cluster setup

The lab must already have Jenkins, Argo CD, and the demo application's `dev` namespace. As an administrator:

```bash
kubectl apply -f kubernetes/dev/namespace.yaml
kubectl apply -f ci/verification-rbac.yaml
```

The file creates the `ci-tests` namespace and `flagship-ci` ServiceAccount in `jenkins`. Adjust the namespace consistently if Jenkins is installed elsewhere.

The delivery agent can create/delete test pods only in `ci-tests`; in `dev` it can read the demo Deployment and workloads and establish port forwards. It can read only the named Argo CD Application. It has no application Deployment write permission, no cluster-wide role, and no permission to read Secrets. Its access to pod logs is limited to the test namespace. Events and application state are archived for diagnosis; treat Jenkins artifacts as operational information and control access accordingly.

If the GHCR image is private, provision a registry pull Secret in **both** `ci-tests` and `dev`, and configure the respective default ServiceAccounts' `imagePullSecrets`. The temporary test pod and the current app use their namespace's default ServiceAccount for image pulls. Do not place registry tokens in Git. This is an administrator setup step; CI cannot create Secrets or patch ServiceAccounts.

The agent's tools container installs pinned `kubectl`, kubeconform, and Trivy releases, verifies release checksums, and uses the existing Alpine tools image. Tools currently target Linux AMD64. Kubernetes schema target `1.31.0` matches the existing kubectl target; verify the actual cluster version and upgrade both deliberately if your lab changes. The Application schema is from Argo CD v3.5.5; see `ci/schemas/README.md`.

## Credentials and trust boundaries

Keep these two Jenkins credential IDs:

- `ghcr-creds`: credentials allowed to publish/read the project's GHCR package, without unrelated repository or administrative privileges. Used only for publishing and scanning, not for the Git push.
- `github-push`: a fine-grained, expiring token restricted to `dionis1/flagship-platform` with repository **Contents: read and write** and metadata access. No organization administration or permission to edit Actions workflows is needed. Do not reuse a broad personal token. A short-lived GitHub App installation token with equivalent repository permissions is a future alternative; it requires separately configured Jenkins token issuance/refresh.

Actual token permissions are configured in GitHub/Jenkins and cannot be enforced by a Jenkinsfile. Audit those settings before enabling automatic delivery. Do not expose these credentials or the delivery ServiceAccount to untrusted builds.

BuildKit remains privileged on a trusted lab node. This exposes a substantial host-isolation risk even with namespace RBAC; RBAC does not contain a privileged container. Do not run untrusted Dockerfiles there. Rootless builds or isolated disposable builder nodes are the next security improvement. The lightweight classification pod and infrastructure-only validation pod are unprivileged and have no API token; skipped and validation-only builds never allocate BuildKit.

## Trigger policy and acceptance checks

The Jenkinsfile does not turn on webhooks or polling. Keep manual triggering until the following tests pass in your job. Configure its SCM branch as `*/main`, use a normal full Git checkout (do not enable shallow history without fetching the comparison base), and restrict who can change job configuration or trusted `main`.

The policy compares Git **content**, never a user-supplied commit message or `[skip ci]` string. `GIT_PREVIOUS_SUCCESSFUL_COMMIT` is supplied by Jenkins' Git plugin; if unavailable, the safe fallback is a full build, except for a provably image-only latest commit.

| Change | Expected action |
| --- | --- |
| `app/**`, `ci/**`, `tests/**`, or `Jenkinsfile` | Build, scan, test, promote, verify |
| Documentation/screenshots only | Skip delivery |
| Only the generated single image-line substitution | Skip delivery |
| Other Kubernetes, Helm, or Argo CD changes | Validate, without publishing or updating Git |
| Application plus manifest/docs changes | Full build |
| Unknown/missing comparison base or first build | Full build, except a provably image-only latest commit |

An SCM webhook can still enqueue one lightweight job for a generated deployment commit. The policy prevents that job from rebuilding or generating another deployment commit. Provider-level filtering can avoid even that job, but depends on your Jenkins job/webhook integration and must be tested there. A manifest-only commit is still reconciled by Argo CD independently of Jenkins; current direct-to-main GitOps cannot make validation a pre-merge admission gate.

Before enabling a main push webhook, perform these controlled checks and retain their Jenkins build URLs:

1. Establish a successful baseline build.
2. Change application content while preserving the expected heading: one full build, scan, HTTP test, promotion, and verified rollout.
3. Observe the generated deployment commit: any follow-up job says `skip`; no new image or deployment commit follows it.
4. Change only documentation: `skip`.
5. Commit an application change and a manifest change together: full build, never skip.
6. Use a temporary test branch/job without deployment credentials to verify a missing heading and an invalid manifest fail. Do not feed deliberately broken manifests into auto-synced `main`.
7. Queue two manual builds. Confirm Jenkins serializes them. A superseded source or competing deployment must fail with a stale-promotion error rather than overwrite the newer image.
8. Confirm a PR/fork job has neither the delivery credentials nor permission to launch privileged delivery pods.

Local tests exercise the classification and Git races with temporary repositories. They do not prove your externally configured webhook or credential scope. The live checks above remain required before automatic builds are enabled.

## Tests

From the repository root, with Python 3 installed:

```bash
python3 -m unittest discover -s tests -v
```

The suite uses temporary Git repositories and loopback HTTP servers. With kubeconform on `PATH`, it additionally proves invalid field types and unknown fields are rejected. Run complete manifest checks with:

```bash
sh ci/validate.sh
```

In the Alpine CI pod, `sh ci/install-tools.sh` installs the toolchain. It is not a host package installer for Ubuntu.

To exercise the built application locally using Docker:

```bash
docker build -t flagship-demo-app:check app
docker run --rm -p 127.0.0.1:8080:80 flagship-demo-app:check
# In another terminal:
python3 ci/http_smoke.py http://127.0.0.1:8080/
```

With the cluster prerequisites and read-only verification permissions configured, the same deployment verification used by Jenkins can also be run manually:

```bash
python3 ci/kube_checks.py deployment \
  --revision <full-deployment-commit-sha> \
  --image ghcr.io/dionis1/flagship-demo-app@sha256:<digest>
```

## Reviewed promotion roadmap

Direct pushes to `main` are retained for this local development lab. A production version should have a build job publish the tested digest, then open an environment PR containing that digest. Required checks and reviewers approve the change; Argo CD watches the protected environment branch/repository. Run deployment verification after merge against the resulting environment commit. A PR without branch protection and required review is not an approval boundary.

The static application is enough to demonstrate failure gates and recovery. Test bad page content, image-pull failure, an unhealthy pod, and a revert of a deployment commit before adding more infrastructure.
