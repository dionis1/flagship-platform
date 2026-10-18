# Argo CD Application schema

`application_v1alpha1.json` is the `openAPIV3Schema` for Application v1alpha1 extracted without modification from the official Argo CD v3.5.5 CRD:

https://github.com/argoproj/argo-cd/blob/v3.5.5/manifests/crds/application-crd.yaml

Upstream license: Apache-2.0. The schema is checked in so CI does not silently use a changing CRD schema. Update it when deliberately changing the target Argo CD version. Kubernetes built-in resources are checked separately against the configured Kubernetes version.
