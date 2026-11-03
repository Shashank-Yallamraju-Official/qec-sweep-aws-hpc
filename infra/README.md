# infra

Terraform for everything that outlives a cluster: the results bucket, the node roles, the CI runners, the Systems Manager documents, the MPI network and the cost guardrails. State lives in a versioned S3 bucket made once by hand; everything else is here.

| File | Owns |
| --- | --- |
| `results.tf` | the results bucket, versioned, with Object Lock keeping every object version a year |
| `node.tf` | the node role: put-only on the bucket, read on the files a node fetches as it boots, Session Manager instead of SSH |
| `deploy.tf` | the two CodeBuild-hosted Actions runners and their roles: `plan` reads on a pull request, `deploy` acts on a merge |
| `install.tf`, `smoke.tf` | the two Systems Manager documents a runner may send to the head node: install the job scripts, run the smoke job |
| `network.tf` | the MPI queue's private subnet, its NAT gateway and an S3 gateway endpoint so results bypass the gateway |
| `budget.tf`, `reaper.tf` | a $50 budget with alerts by email, and an hourly Lambda that ends stray instances |
| `spot.tf` | the service-linked role EC2 needs before it will launch spot |

## Commands

```sh
terraform -chdir=infra plan
terraform -chdir=infra apply
```

A pull request plans; a merge applies, through the `infra` workflow on the runners above. The runners exist because the account's managed policy denies every IAM identity-provider action, which rules out GitHub's OIDC federation: CodeBuild hosts the runner and carries the role instead.

## Where it fits

[`cluster/`](../cluster/README.md) names the policies and the bucket by ARN; [`jobs/`](../jobs/README.md) is what the install document ships. The reaper's handler is tested with `uv run pytest tests/infra`.
