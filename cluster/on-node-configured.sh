#!/usr/bin/env bash
# Runs on every node once ParallelCluster has configured it.
set -euo pipefail

# Jobs run inside the Apptainer image, and the AMI does not ship Apptainer.
if ! command -v apptainer >/dev/null; then
  curl -sSL -o /tmp/apptainer.deb \
    https://github.com/apptainer/apptainer/releases/download/v1.5.5/apptainer_1.5.5_amd64.deb
  export DEBIAN_FRONTEND=noninteractive
  # The AMI ships without package lists, and the package has dependencies to resolve.
  apt-get update -q >/dev/null
  apt-get install -y -q /tmp/apptainer.deb >/dev/null
fi

# A fresh EFS mount is root-owned; users need to write to scratch.
if [[ -d /scratch ]]; then
  chmod 1777 /scratch
fi
