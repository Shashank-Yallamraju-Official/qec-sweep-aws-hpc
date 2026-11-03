# cluster

The cluster as code. `cluster.yaml` is the x86 cluster: a head node, a sweep queue of `c7a.large` and `c7i.large` on demand, a spot copy of it, an MPI queue of `hpc6a.48xlarge` with EFA in a private subnet, a login node with Amazon DCV, and EFS as shared scratch. `graviton.yaml` is a sibling cluster of `c8g.large` nodes, since ParallelCluster holds every queue to its head node's architecture. Compute scales to zero three minutes after it goes idle.

## Commands

```sh
pcluster create-cluster --cluster-name qec --cluster-configuration cluster/cluster.yaml --region us-east-2
pcluster delete-cluster --cluster-name qec --region us-east-2
pcluster build-image -c cluster/ami.yaml -i qec-x86 --region us-east-2        # bake Apptainer and the images into an AMI
cluster/dcv-session.sh -t                                                      # open the login node's desktop at https://localhost:8443
```

Nodes boot from the baked AMI, so a sweep's first cell starts about three minutes after submission. `on-node-configured.sh` runs on every node as it boots: it installs Apptainer where the AMI lacks it, makes scratch writable, and puts ParaView on the login node. Nothing on the cluster is reachable from the internet: there is no key pair, commands travel through Systems Manager, and the desktop through a port forward with a certificate the browser trusts.

## Where it fits

A pull request dry-runs both configurations against the account; a merge applies `cluster.yaml` to a running cluster through the deploy workflow. Creating and deleting a cluster stays a hand's decision, since it costs money. The node roles and the files nodes fetch as they boot are in [`infra/`](../infra/README.md). Test the scripts with `uv run pytest tests/cluster`.
