# GitHub Actions reaches this project through two roles and no long-lived key.
# A pull request assumes `plan`, which can read everything and change nothing,
# enough for `terraform plan` and a ParallelCluster dry run. A push to main
# assumes `deploy`, which holds what ParallelCluster documents for its own user
# plus what Terraform needs for the resources in this directory, by name.

locals {
  account         = data.aws_caller_identity.current.account_id
  github_oidc     = "token.actions.githubusercontent.com"
  parallelcluster = "arn:aws:iam::${local.account}:role/parallelcluster/*"
}

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://${local.github_oidc}"
  client_id_list = ["sts.amazonaws.com"]
  # GitHub's root certificate thumbprints; AWS now checks the chain itself, but
  # the argument is required.
  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1c58a3a8518e8759bf075b76b750d4f2df264fcd",
  ]
}

data "aws_iam_policy_document" "github_assume" {
  for_each = {
    plan   = ["repo:${var.github_repository}:pull_request", "repo:${var.github_repository}:ref:refs/heads/main"]
    deploy = ["repo:${var.github_repository}:ref:refs/heads/main"]
  }
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.github_oidc}:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "${local.github_oidc}:sub"
      values   = each.value
    }
  }
}

resource "aws_iam_role" "plan" {
  name               = "qec-sweep-plan"
  assume_role_policy = data.aws_iam_policy_document.github_assume["plan"].json
}

resource "aws_iam_role_policy_attachment" "plan_read" {
  role       = aws_iam_role.plan.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

resource "aws_iam_role" "deploy" {
  name               = "qec-sweep-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_assume["deploy"].json
}

# What ParallelCluster documents as its base user policy, less the Batch, FSx
# and Secrets Manager statements this cluster has no use for.
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
      "arn:aws:iam::${local.account}:oidc-provider/${local.github_oidc}",
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
  role       = aws_iam_role.deploy.name
  policy_arn = each.value.arn
}
