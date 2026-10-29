data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "results" {
  bucket = "qec-sweep-results-${data.aws_caller_identity.current.account_id}"
}
