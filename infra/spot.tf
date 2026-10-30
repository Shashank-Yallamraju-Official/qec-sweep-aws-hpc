# EC2 refuses spot launches until this role exists, and the cluster's node roles
# are not allowed to create it; a fresh account does not have it.
resource "aws_iam_service_linked_role" "spot" {
  aws_service_name = "spot.amazonaws.com"
}
