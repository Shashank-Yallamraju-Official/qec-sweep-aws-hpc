data "aws_caller_identity" "current" {}

# Results outlive the cluster, so nothing here expires them or lets
# `terraform destroy` empty the bucket.
resource "aws_s3_bucket" "results" {
  bucket = "qec-sweep-results-${data.aws_caller_identity.current.account_id}"
}
