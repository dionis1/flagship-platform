#!/bin/sh
set -eu
# Pinned releases; release checksums detect download corruption.
# CI agents are Linux AMD64, matching the existing lab.
test "$(uname -m)" = x86_64
apk add --no-cache curl git python3 ca-certificates
mkdir -p reports
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cd "$work"
fetch() { curl --fail --location --silent --show-error --retry 3 --connect-timeout 10 --max-time 180 "$1" -o "$2"; }
fetch https://dl.k8s.io/release/v1.31.0/bin/linux/amd64/kubectl kubectl
fetch https://dl.k8s.io/release/v1.31.0/bin/linux/amd64/kubectl.sha256 kubectl.sha256
printf '%s  kubectl\n' "$(cat kubectl.sha256)" | sha256sum -c -
install -m 0755 kubectl /usr/local/bin/kubectl
fetch https://github.com/yannh/kubeconform/releases/download/v0.8.0/kubeconform-linux-amd64.tar.gz kubeconform-linux-amd64.tar.gz
fetch https://github.com/yannh/kubeconform/releases/download/v0.8.0/CHECKSUMS CHECKSUMS
grep ' kubeconform-linux-amd64.tar.gz$' CHECKSUMS | sha256sum -c -
tar -xzf kubeconform-linux-amd64.tar.gz kubeconform
install -m 0755 kubeconform /usr/local/bin/kubeconform
fetch https://github.com/aquasecurity/trivy/releases/download/v0.76.0/trivy_0.76.0_Linux-64bit.tar.gz trivy_0.76.0_Linux-64bit.tar.gz
fetch https://github.com/aquasecurity/trivy/releases/download/v0.76.0/trivy_0.76.0_checksums.txt trivy_checksums.txt
grep ' trivy_0.76.0_Linux-64bit.tar.gz$' trivy_checksums.txt | sha256sum -c -
tar -xzf trivy_0.76.0_Linux-64bit.tar.gz trivy
install -m 0755 trivy /usr/local/bin/trivy
