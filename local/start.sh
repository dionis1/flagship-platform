#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
.local/bin/k3d cluster start flagship-platform
