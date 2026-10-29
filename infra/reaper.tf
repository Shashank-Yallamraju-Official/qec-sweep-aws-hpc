locals {
  reaper = "qec-sweep-reaper"
}

resource "aws_sns_topic" "alerts" {
  name = "qec-sweep-alerts"
}

resource "aws_sns_topic_subscription" "alerts_email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

data "archive_file" "reaper" {
  type        = "zip"
  source_file = "${path.module}/reaper/handler.py"
  output_path = "${path.module}/.terraform/reaper.zip"
}

data "aws_iam_policy_document" "reaper_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "reaper" {
  statement {
    actions   = ["ec2:DescribeInstances"]
    resources = ["*"]
  }
  statement {
    actions   = ["ec2:TerminateInstances"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/project"
      values   = ["qec-sweep"]
    }
  }
  statement {
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.alerts.arn]
  }
  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.reaper.arn}:*"]
  }
}

resource "aws_iam_role" "reaper" {
  name               = local.reaper
  assume_role_policy = data.aws_iam_policy_document.reaper_assume.json
}

resource "aws_iam_role_policy" "reaper" {
  role   = aws_iam_role.reaper.id
  policy = data.aws_iam_policy_document.reaper.json
}

resource "aws_cloudwatch_log_group" "reaper" {
  name              = "/aws/lambda/${local.reaper}"
  retention_in_days = 14
}

resource "aws_lambda_function" "reaper" {
  function_name    = local.reaper
  role             = aws_iam_role.reaper.arn
  runtime          = "python3.12"
  handler          = "handler.handler"
  filename         = data.archive_file.reaper.output_path
  source_code_hash = data.archive_file.reaper.output_base64sha256
  timeout          = 30

  environment {
    variables = {
      TOPIC_ARN = aws_sns_topic.alerts.arn
      MAX_HOURS = var.max_instance_hours
    }
  }

  depends_on = [aws_cloudwatch_log_group.reaper, aws_iam_role_policy.reaper]
}

resource "aws_cloudwatch_event_rule" "hourly" {
  name                = "${local.reaper}-hourly"
  schedule_expression = "rate(1 hour)"
}

resource "aws_cloudwatch_event_target" "reaper" {
  rule = aws_cloudwatch_event_rule.hourly.name
  arn  = aws_lambda_function.reaper.arn
}

resource "aws_lambda_permission" "hourly" {
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.reaper.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.hourly.arn
}
