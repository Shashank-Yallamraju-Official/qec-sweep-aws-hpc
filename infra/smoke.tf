# The smoke job is the one thing a pull request may run on the cluster. It goes
# through a fixed Systems Manager document rather than a shell, so the
# read-only runner can be allowed to send exactly this and nothing else, and
# only to the head node of this cluster.
resource "aws_ssm_document" "smoke" {
  name            = "qec-sweep-smoke"
  document_type   = "Command"
  document_format = "YAML"
  content = yamlencode({
    schemaVersion = "2.2"
    description   = "run the smoke job from the given commit's job scripts as the cluster user"
    parameters = {
      jobs = {
        type        = "String"
        description = "S3 URI of a tar.gz holding the jobs directory"
        default     = "s3://${aws_s3_bucket.results.bucket}/cluster/jobs.tgz"
      }
    }
    mainSteps = [{
      action = "aws:runShellScript"
      name   = "smoke"
      inputs = {
        timeoutSeconds = "900"
        runCommand = [
          "#!/bin/bash",
          "set -euo pipefail",
          "# The job's output lands beside the script, so it must be on the shared scratch,",
          "# not the head node's own /tmp, which the compute nodes never see.",
          "work=$(mktemp -d /scratch/smoke.XXXXXX)",
          "aws s3 cp --quiet '{{ jobs }}' \"$work/jobs.tgz\"",
          "tar xzf \"$work/jobs.tgz\" -C \"$work\" --warning=no-unknown-keyword && chown -R ubuntu:ubuntu \"$work\"",
          "cd \"$work\" && runuser -u ubuntu -- env PATH=/opt/slurm/bin:$PATH sbatch --wait --parsable jobs/smoke.sbatch > job.id",
          "cat \"smoke-$(cat job.id).out\"",
        ]
      }
    }]
  })
}

data "aws_iam_policy_document" "smoke" {
  statement {
    sid       = "SendTheDocument"
    actions   = ["ssm:SendCommand"]
    resources = [aws_ssm_document.smoke.arn]
  }
  statement {
    sid       = "ToTheHeadNode"
    actions   = ["ssm:SendCommand"]
    resources = ["arn:aws:ec2:${var.region}:${local.account}:instance/*"]
    condition {
      test     = "StringEquals"
      variable = "ssm:resourceTag/parallelcluster:node-type"
      values   = ["HeadNode"]
    }
  }
}

resource "aws_iam_role_policy" "plan_smoke" {
  role   = aws_iam_role.runner["plan"].name
  name   = "smoke"
  policy = data.aws_iam_policy_document.smoke.json
}
