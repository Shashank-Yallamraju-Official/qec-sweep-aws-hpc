output "results_bucket" {
  value = aws_s3_bucket.results.bucket
}

output "node_instance_profile" {
  value = aws_iam_instance_profile.node.name
}
