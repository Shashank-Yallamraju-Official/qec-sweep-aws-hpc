output "results_bucket" {
  value = aws_s3_bucket.results.bucket
}

output "node_instance_profile" {
  value = aws_iam_instance_profile.node.name
}

output "node_results_policy" {
  value = aws_iam_policy.node_results.arn
}

output "mpi_subnet_id" {
  value = aws_subnet.mpi.id
}

output "plan_runner" {
  value       = aws_codebuild_project.runner["plan"].name
  description = "runs-on: codebuild-<this>-$${{ github.run_id }}-$${{ github.run_attempt }} for pull requests"
}

output "deploy_runner" {
  value       = aws_codebuild_project.runner["deploy"].name
  description = "the same label form, for jobs on main"
}

output "runner_webhooks" {
  value       = { for k, w in aws_codebuild_webhook.runner : k => { url = w.payload_url, secret = w.secret } }
  sensitive   = true
  description = "what each GitHub repository hook must carry; see infra/deploy.tf"
}
