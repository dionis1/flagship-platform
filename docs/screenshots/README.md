# Project screenshots

Capture these four views from the running platform and save them in this directory:

| Filename | What the screenshot should show |
| --- | --- |
| `jenkins-pipeline.png` | A successful build with pipeline stages, build number, and published image tag visible. |
| `argocd-healthy.png` | The `demo-app-dev` Application showing **Synced** and **Healthy**, ideally with its Git revision and workload tree. |
| `datadog-cluster.png` | The `devops-portfolio` cluster with nodes or workloads and populated metrics; include the time range. |
| `demo-app.png` | The application served by the Kubernetes workload, accessed through port forwarding or its configured endpoint. |

Use the same deployment for the Jenkins, Argo CD, and application captures where possible. Record the capture date, source commit, image tag, and any relevant build number alongside the images so reviewers can connect the evidence to the code.

Before publishing, crop or redact credentials, API keys, tokens, and unrelated private information. Keep the status indicators and project identifiers readable.

Once the actual files are added, replace the pending paragraph in the main README's **Project evidence** section with these embeds and short captions:

```markdown
### Successful Jenkins pipeline
![Successful Jenkins pipeline](docs/screenshots/jenkins-pipeline.png)

### Argo CD: Synced and Healthy
![Argo CD Application showing Synced and Healthy](docs/screenshots/argocd-healthy.png)

### Datadog cluster monitoring
![Datadog cluster view with workload metrics](docs/screenshots/datadog-cluster.png)

### Running demo application
![Demo application running on Kubernetes](docs/screenshots/demo-app.png)
```

These are capture instructions. No screenshots have been added yet.
