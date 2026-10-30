# GitHub Actions reaches this project without a long-lived key. The managed
# organisation policy denies every iam:*Provider* action, so GitHub's OIDC
# federation is not available here; instead CodeBuild hosts the Actions runners
# and each runner carries a service role. A pull request's jobs run on `plan`,
# which can read everything and change nothing, enough for `terraform plan` and
# a ParallelCluster dry run. Jobs on main run on `deploy`, which holds what
# ParallelCluster documents for its own user plus what Terraform needs for the
# resources in this directory, by name.

# The GitHub connection itself is made in the console, once, because installing
# the GitHub app is the one step that needs a browser; Terraform takes its ARN.
locals {
  account         = data.aws_caller_identity.current.account_id
  repository_url  = "https://github.com/${var.github_repository}.git"
  parallelcluster = "arn:aws:iam::${local.account}:role/parallelcluster/*"
  runners         = toset(["plan", "deploy"])
}

data "aws_iam_policy_document" "codebuild_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["codebuild.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account]
    }
  }
}

resource "aws_iam_role" "runner" {
  for_each           = local.runners
  name               = "qec-sweep-${each.key}"
  assume_role_policy = data.aws_iam_policy_document.codebuild_assume.json
}

# What any runner needs of its own: its build log and the connection it clones through.
data "aws_iam_policy_document" "runner" {
  statement {
    sid       = "BuildLog"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:${var.region}:${local.account}:log-group:/aws/codebuild/qec-sweep-*"]
  }
  statement {
    sid       = "Clone"
    actions   = ["codeconnections:GetConnectionToken", "codeconnections:GetConnection", "codeconnections:UseConnection"]
    resources = [var.github_connection_arn]
  }
}

resource "aws_iam_role_policy" "runner" {
  for_each = local.runners
  role     = aws_iam_role.runner[each.key].name
  name     = "runner"
  policy   = data.aws_iam_policy_document.runner.json
}

resource "aws_iam_role_policy_attachment" "plan_read" {
  role       = aws_iam_role.runner["plan"].name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

resource "aws_codebuild_project" "runner" {
  for_each     = local.runners
  name         = "qec-sweep-${each.key}"
  description  = "GitHub Actions runner for the qec-sweep ${each.key} jobs"
  service_role = aws_iam_role.runner[each.key].arn
  source {
    type     = "GITHUB"
    location = local.repository_url
    auth {
      type     = "CODECONNECTIONS"
      resource = var.github_connection_arn
    }
  }
  artifacts {
    type = "NO_ARTIFACTS"
  }
  environment {
    type         = "LINUX_CONTAINER"
    compute_type = "BUILD_GENERAL1_SMALL"
    image        = "aws/codebuild/amazonlinux-x86_64-standard:5.0"
  }
  logs_config {
    cloudwatch_logs {
      group_name = "/aws/codebuild/qec-sweep-${each.key}"
    }
  }
}

# A queued Actions job whose runs-on label names a project lands on it. A job
# queued event cannot be filtered by branch, so the deploy project insists on
# the workflow named deploy, which only runs on main, and on the repository
# owner as the actor: a pull request that edits a workflow to ask for the
# deploy runner gets nothing.
# GitHub refused to let CodeBuild register these hooks itself through the app
# installation, so CodeBuild only issues the endpoint and secret here and the
# repository's hooks are created once by hand from the outputs below:
#   gh api repos/<repo>/hooks -f 'events[]=workflow_job' -f config[url]=<payload_url>
#     -f config[secret]=<secret> -f config[content_type]=json
resource "aws_codebuild_webhook" "runner" {
  for_each        = local.runners
  project_name    = aws_codebuild_project.runner[each.key].name
  build_type      = "BUILD"
  manual_creation = true
  filter_group {
    filter {
      type    = "EVENT"
      pattern = "WORKFLOW_JOB_QUEUED"
    }
    dynamic "filter" {
      for_each = each.key == "deploy" ? { WORKFLOW_NAME = "^deploy$", ACTOR_ACCOUNT_ID = "^${var.github_actor_id}$" } : {}
      content {
        type    = filter.key
        pattern = filter.value
      }
    }
  }
}

data "aws_iam_policy_document" "pcluster" {
  statement {
    sid       = "Ec2"
    actions   = ["ec2:Describe*"]
    resources = ["*"]
  }
  statement {
    sid = "Ec2Write"
    actions = [
      "ec2:AllocateAddress", "ec2:AssociateAddress", "ec2:AttachNetworkInterface",
      "ec2:AuthorizeSecurityGroupEgress", "ec2:AuthorizeSecurityGroupIngress",
      "ec2:CreateFleet", "ec2:CreateLaunchTemplate", "ec2:CreateLaunchTemplateVersion",
      "ec2:CreateNetworkInterface", "ec2:CreatePlacementGroup", "ec2:CreateSecurityGroup",
      "ec2:CreateSnapshot", "ec2:CreateTags", "ec2:DeleteTags", "ec2:CreateVolume",
      "ec2:DeleteLaunchTemplate", "ec2:DeleteNetworkInterface", "ec2:DeletePlacementGroup",
      "ec2:DeleteSecurityGroup", "ec2:DeleteVolume", "ec2:DisassociateAddress",
      "ec2:ModifyLaunchTemplate", "ec2:ModifyNetworkInterfaceAttribute", "ec2:ModifyVolume",
      "ec2:ModifyVolumeAttribute", "ec2:ReleaseAddress", "ec2:RevokeSecurityGroupEgress",
      "ec2:RevokeSecurityGroupIngress", "ec2:RunInstances", "ec2:TerminateInstances",
    ]
    resources = ["*"]
  }
  statement {
    sid = "DynamoDb"
    actions = [
      "dynamodb:DescribeTable", "dynamodb:ListTagsOfResource", "dynamodb:CreateTable",
      "dynamodb:DeleteTable", "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
      "dynamodb:Query", "dynamodb:TagResource", "dynamodb:UntagResource",
    ]
    resources = ["arn:aws:dynamodb:*:${local.account}:table/parallelcluster-*"]
  }
  statement {
    sid = "Route53"
    actions = [
      "route53:ChangeResourceRecordSets", "route53:ChangeTagsForResource", "route53:CreateHostedZone",
      "route53:DeleteHostedZone", "route53:GetChange", "route53:GetHostedZone",
      "route53:ListResourceRecordSets", "route53:ListQueryLoggingConfigs",
    ]
    resources = ["*"]
  }
  statement {
    sid       = "CloudFormation"
    actions   = ["cloudformation:*"]
    resources = ["*"]
  }
  statement {
    sid = "CloudWatch"
    actions = [
      "cloudwatch:PutDashboard", "cloudwatch:ListDashboards", "cloudwatch:DeleteDashboards",
      "cloudwatch:GetDashboard", "cloudwatch:PutMetricAlarm", "cloudwatch:DeleteAlarms",
      "cloudwatch:DescribeAlarms", "cloudwatch:PutCompositeAlarm", "cloudwatch:TagResource",
      "cloudwatch:UntagResource",
    ]
    resources = ["*"]
  }
  statement {
    sid = "IamRead"
    actions = [
      "iam:GetRole", "iam:GetRolePolicy", "iam:GetPolicy", "iam:SimulatePrincipalPolicy",
      "iam:GetInstanceProfile",
    ]
    resources = [
      "arn:aws:iam::${local.account}:role/*", "arn:aws:iam::${local.account}:policy/*",
      "arn:aws:iam::aws:policy/*", "arn:aws:iam::${local.account}:instance-profile/*",
    ]
  }
  statement {
    sid = "IamInstanceProfile"
    actions = [
      "iam:CreateInstanceProfile", "iam:DeleteInstanceProfile", "iam:AddRoleToInstanceProfile",
      "iam:RemoveRoleFromInstanceProfile",
    ]
    resources = ["arn:aws:iam::${local.account}:instance-profile/parallelcluster/*"]
  }
  statement {
    sid       = "IamPassRole"
    actions   = ["iam:PassRole"]
    resources = [local.parallelcluster]
    condition {
      test     = "StringEqualsIfExists"
      variable = "iam:PassedToService"
      values   = ["lambda.amazonaws.com", "ec2.amazonaws.com", "spotfleet.amazonaws.com"]
    }
  }
  statement {
    sid = "Lambda"
    actions = [
      "lambda:CreateFunction", "lambda:DeleteFunction", "lambda:GetFunctionConfiguration",
      "lambda:GetFunction", "lambda:InvokeFunction", "lambda:AddPermission", "lambda:RemovePermission",
      "lambda:UpdateFunctionConfiguration", "lambda:TagResource", "lambda:ListTags", "lambda:UntagResource",
    ]
    resources = [
      "arn:aws:lambda:*:${local.account}:function:parallelcluster-*",
      "arn:aws:lambda:*:${local.account}:function:pcluster-*",
    ]
  }
  statement {
    sid       = "S3ParallelCluster"
    actions   = ["s3:*"]
    resources = ["arn:aws:s3:::parallelcluster-*", "arn:aws:s3:::aws-parallelcluster-*"]
  }
  statement {
    sid       = "S3ParallelClusterRead"
    actions   = ["s3:Get*", "s3:List*"]
    resources = ["arn:aws:s3:::*-aws-parallelcluster*"]
  }
  statement {
    sid       = "Efs"
    actions   = ["elasticfilesystem:*"]
    resources = ["arn:aws:elasticfilesystem:*:${local.account}:*"]
  }
  statement {
    sid = "Logs"
    actions = [
      "logs:DeleteLogGroup", "logs:PutRetentionPolicy", "logs:DescribeLogGroups", "logs:CreateLogGroup",
      "logs:TagResource", "logs:UntagResource", "logs:FilterLogEvents", "logs:GetLogEvents",
      "logs:CreateExportTask", "logs:DescribeLogStreams", "logs:DescribeExportTasks",
      "logs:DescribeMetricFilters", "logs:PutMetricFilter", "logs:DeleteMetricFilter", "logs:ListTagsForResource",
    ]
    resources = ["*"]
  }
  statement {
    sid       = "ResourceGroupsAndTags"
    actions   = ["resource-groups:ListGroupResources", "resource-groups:GetGroupConfiguration", "tag:GetResources"]
    resources = ["*"]
  }
}

# ParallelCluster's privileged IAM mode: it creates the cluster's own roles under
# the parallelcluster/ path and may attach only the policies named here, which
# include the two the cluster configuration asks for.
data "aws_iam_policy_document" "pcluster_iam" {
  statement {
    sid = "Roles"
    actions = [
      "iam:CreateRole", "iam:DeleteRole", "iam:TagRole", "iam:UntagRole", "iam:CreateServiceLinkedRole",
      "iam:PutRolePolicy", "iam:DeleteRolePolicy",
    ]
    resources = [local.parallelcluster]
  }
  statement {
    sid       = "Policies"
    actions   = ["iam:AttachRolePolicy", "iam:DetachRolePolicy"]
    resources = [local.parallelcluster]
    condition {
      test     = "ArnLike"
      variable = "iam:PolicyARN"
      values = [
        "arn:aws:iam::${local.account}:policy/parallelcluster*",
        "arn:aws:iam::${local.account}:policy/parallelcluster/*",
        "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy",
        "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
        "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
        aws_iam_policy.node_results.arn,
      ]
    }
  }
}

# What Terraform needs for this directory, by resource name where the service
# supports it: the two buckets, the qec-sweep-* roles, policies, functions, log
# groups, rules and topic, the budget, the OIDC provider, and the MPI subnet's
# network pieces, which EC2 cannot scope by name.
data "aws_iam_policy_document" "terraform" {
  statement {
    sid     = "Buckets"
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.results.arn, "${aws_s3_bucket.results.arn}/*",
      "arn:aws:s3:::qec-sweep-tfstate-${local.account}", "arn:aws:s3:::qec-sweep-tfstate-${local.account}/*",
    ]
  }
  statement {
    sid     = "OwnIam"
    actions = ["iam:*"]
    resources = [
      "arn:aws:iam::${local.account}:role/qec-sweep-*",
      "arn:aws:iam::${local.account}:policy/qec-sweep-*",
      "arn:aws:iam::${local.account}:instance-profile/qec-sweep-*",
      "arn:aws:iam::${local.account}:role/aws-service-role/spot.amazonaws.com/*",
    ]
  }
  statement {
    sid     = "Reaper"
    actions = ["lambda:*", "logs:*", "events:*"]
    resources = [
      "arn:aws:lambda:${var.region}:${local.account}:function:qec-sweep-*",
      "arn:aws:logs:${var.region}:${local.account}:log-group:/aws/lambda/qec-sweep-*",
      "arn:aws:logs:${var.region}:${local.account}:log-group:/aws/lambda/qec-sweep-*:*",
      "arn:aws:events:${var.region}:${local.account}:rule/qec-sweep-*",
    ]
  }
  statement {
    sid       = "AlertsAndBudget"
    actions   = ["sns:*", "budgets:*"]
    resources = ["arn:aws:sns:${var.region}:${local.account}:qec-sweep-*", "arn:aws:budgets::${local.account}:budget/*"]
  }
  statement {
    sid = "Network"
    actions = [
      "ec2:CreateSubnet", "ec2:DeleteSubnet", "ec2:ModifySubnetAttribute",
      "ec2:CreateRouteTable", "ec2:DeleteRouteTable", "ec2:AssociateRouteTable", "ec2:DisassociateRouteTable",
      "ec2:CreateRoute", "ec2:DeleteRoute", "ec2:CreateVpcEndpoint", "ec2:DeleteVpcEndpoints",
      "ec2:ModifyVpcEndpoint", "ec2:CreateNatGateway", "ec2:DeleteNatGateway",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "deploy" {
  for_each = {
    pcluster     = data.aws_iam_policy_document.pcluster.json
    pcluster-iam = data.aws_iam_policy_document.pcluster_iam.json
    terraform    = data.aws_iam_policy_document.terraform.json
  }
  name   = "qec-sweep-deploy-${each.key}"
  policy = each.value
}

resource "aws_iam_role_policy_attachment" "deploy" {
  for_each   = aws_iam_policy.deploy
  role       = aws_iam_role.runner["deploy"].name
  policy_arn = each.value.arn
}
