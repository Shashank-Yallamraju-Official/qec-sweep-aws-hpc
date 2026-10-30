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

output "plan_role_arn" {
  value       = aws_iam_role.plan.arn
  description = "assumed by pull-request workflows"
}

output "deploy_role_arn" {
  value       = aws_iam_role.deploy.arn
  description = "assumed by workflows on main"
}
