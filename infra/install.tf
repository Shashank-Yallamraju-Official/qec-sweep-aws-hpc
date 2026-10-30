# A merge to main installs the job scripts on the head node through a second
# fixed document: the deploy runner may send this one and the smoke one, and
# nothing else, to the head node. The scripts land under /opt/qec/jobs with the
# commit they came from beside them, which every run then records.
resource "aws_ssm_document" "install_jobs" {
  name            = "qec-sweep-install-jobs"
  document_type   = "Command"
  document_format = "YAML"
  content = yamlencode({
    schemaVersion = "2.2"
    description   = "install the jobs directory from a tar.gz in S3 and record its commit"
    parameters = {
      jobs = {
        type        = "String"
        description = "S3 URI of a tar.gz holding the jobs directory"
      }
      commit = {
        type           = "String"
        description    = "the commit the archive was made from"
        allowedPattern = "^[0-9a-f]{40}$"
      }
    }
    mainSteps = [{
      action = "aws:runShellScript"
      name   = "install"
      inputs = {
        timeoutSeconds = "300"
        runCommand = [
          "#!/bin/bash",
          "set -euo pipefail",
          "work=$(mktemp -d)",
          "aws s3 cp --quiet '{{ jobs }}' \"$work/jobs.tgz\"",
          "tar xzf \"$work/jobs.tgz\" -C \"$work\"",
          "echo '{{ commit }}' > \"$work/jobs/COMMIT\"",
          "chmod +x \"$work\"/jobs/*.sh && chown -R root:root \"$work/jobs\"",
          "rm -rf /opt/qec/jobs && mkdir -p /opt/qec && mv \"$work/jobs\" /opt/qec/jobs",
          "echo \"installed jobs from {{ commit }}\"",
        ]
      }
    }]
  })
}

data "aws_iam_policy_document" "deploy_head" {
  statement {
    sid       = "SendTheDocuments"
    actions   = ["ssm:SendCommand"]
    resources = [aws_ssm_document.install_jobs.arn, aws_ssm_document.smoke.arn]
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
  statement {
    sid       = "ReadTheOutcome"
    actions   = ["ssm:GetCommandInvocation", "ssm:ListCommands", "ec2:DescribeInstances"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "deploy_head" {
  role   = aws_iam_role.runner["deploy"].name
  name   = "head-node"
  policy = data.aws_iam_policy_document.deploy_head.json
}
