data "aws_iam_policy_document" "node_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "node" {
  name               = "qec-sweep-node"
  assume_role_policy = data.aws_iam_policy_document.node_assume.json
}

# Session Manager stands in for SSH: no key pair and no open port.
resource "aws_iam_role_policy_attachment" "node_ssm" {
  role       = aws_iam_role.node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "node_results" {
  statement {
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.results.arn}/*"]
  }
}

# A managed policy so the cluster's own node roles can attach the same put-only
# access instead of a broader one of their own.
resource "aws_iam_policy" "node_results" {
  name   = "qec-sweep-node-results"
  policy = data.aws_iam_policy_document.node_results.json
}

resource "aws_iam_role_policy_attachment" "node_results" {
  role       = aws_iam_role.node.name
  policy_arn = aws_iam_policy.node_results.arn
}

resource "aws_iam_instance_profile" "node" {
  name = "qec-sweep-node"
  role = aws_iam_role.node.name
}
