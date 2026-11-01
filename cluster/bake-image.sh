#!/usr/bin/env bash
# Runs once, on the instance an AMI is built from: installs Apptainer and pulls the
# images into /opt/images, so a node booted from the AMI starts a job without doing
# either. jobs/pull-image.sh looks there first, by digest, before the shared cache.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
registry=oras://ghcr.io/shashank-yallamraju-official/qec-sweep-aws-hpc

# The same package the configure script installs, from its release rather than the
# bucket, since the build instance has no role on the bucket; the digest is the same.
deb=apptainer_1.5.5_amd64.deb
curl -fsSL -o "/tmp/$deb" "https://github.com/apptainer/apptainer/releases/download/v1.5.5/$deb"
echo "25095d3711504b3e8657dbb2e172ef8db9db43c4503d940c9c36b105db8dce77  /tmp/$deb" | sha256sum -c --quiet
apt-get update -q >/dev/null
apt-get install -y -q "/tmp/$deb" >/dev/null
rm -f "/tmp/$deb"

# Whatever main's images are at bake time. A run whose image is newer than the AMI
# pulls it into the shared cache as before; the AMI just makes the common case free.
mkdir -p /opt/images
for name in sweep mpi; do
  digest=$(apptainer pull --force /opt/images/.pull "$registry/$name:latest" 2>&1 | tee >(cat >&2) | sed -n 's/^INFO: *Digest: *//p')
  [[ $digest == sha256:* ]] || { echo "no digest pulled for $name" >&2; exit 1; }
  mv /opt/images/.pull "/opt/images/${digest#sha256:}.sif"
done
rm -rf /root/.apptainer
ls -l /opt/images
