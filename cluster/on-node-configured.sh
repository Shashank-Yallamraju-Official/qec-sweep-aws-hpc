#!/usr/bin/env bash
# Runs on every node once ParallelCluster has configured it.
set -euo pipefail

# Jobs run inside the Apptainer image. A node from the baked AMI (cluster/ami.yaml)
# already has it and skips this; a node from the stock AMI installs it here. The
# x86 package is staged in the bucket so a scale-up never waits on GitHub, and is
# checked against a pinned digest before anything installs it as root. Apptainer
# publishes no arm64 package, so a Graviton node takes the one from its PPA.
if ! command -v apptainer >/dev/null; then
  export DEBIAN_FRONTEND=noninteractive
  case $(dpkg --print-architecture) in
    amd64)
      deb=apptainer_1.5.5_amd64.deb
      aws s3 cp --quiet "s3://qec-sweep-results-523520772490/cluster/$deb" "/tmp/$deb"
      echo "25095d3711504b3e8657dbb2e172ef8db9db43c4503d940c9c36b105db8dce77  /tmp/$deb" | sha256sum -c --quiet
      # The AMI ships without package lists, and the package has dependencies to resolve.
      apt-get update -q >/dev/null
      apt-get install -y -q "/tmp/$deb" >/dev/null
      ;;
    arm64)
      add-apt-repository -y ppa:apptainer/ppa >/dev/null
      apt-get install -y -q apptainer >/dev/null
      ;;
  esac
fi

# A fresh EFS mount is root-owned; users need to write to scratch.
if [[ -d /scratch ]]; then
  chmod 1777 /scratch
fi
