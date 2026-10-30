data "aws_caller_identity" "current" {}

# Results outlive the cluster, so nothing here expires them or lets
# `terraform destroy` empty the bucket.
resource "aws_s3_bucket" "results" {
  bucket = "qec-sweep-results-${data.aws_caller_identity.current.account_id}"
}

# Results are evidence. Versioning keeps every object that was ever put under a
# key, and the lock keeps each version for a year, so a result can be published
# again under its name but never silently replaced or deleted. Governance mode,
# not compliance: an administrator with s3:BypassGovernanceRetention can still
# undo a mistake, where compliance mode would hold it for the full year.
resource "aws_s3_bucket_versioning" "results" {
  bucket = aws_s3_bucket.results.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_object_lock_configuration" "results" {
  bucket = aws_s3_bucket.results.id
  rule {
    default_retention {
      mode = "GOVERNANCE"
      days = 365
    }
  }
  depends_on = [aws_s3_bucket_versioning.results]
}
