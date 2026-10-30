variable "region" {
  type    = string
  default = "us-east-2"
}

variable "alert_email" {
  type        = string
  description = "where budget alerts go; set in terraform.tfvars or TF_VAR_alert_email"
}

variable "max_instance_hours" {
  type        = number
  default     = 4
  description = "age at which the reaper terminates an instance outside a cluster"
}

variable "public_subnet_id" {
  type        = string
  default     = "subnet-0b765c6a2d2523330"
  description = "the head node's subnet; the MPI subnet shares its VPC and zone"
}

variable "mpi_subnet_cidr" {
  type        = string
  default     = "172.31.48.0/20"
  description = "the private subnet for the MPI queue"
}

variable "nat_gateway" {
  type        = bool
  default     = false
  description = "give the MPI subnet a NAT gateway; it bills by the hour, so true only while the cluster exists"
}

variable "github_repository" {
  type        = string
  default     = "Shashank-Yallamraju-Official/qec-sweep-aws-hpc"
  description = "the repository whose Actions may assume the plan and deploy roles"
}
