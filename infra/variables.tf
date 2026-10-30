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
  description = "the repository whose Actions run on the plan and deploy runners"
}

variable "github_actor_id" {
  type        = string
  default     = "245481804"
  description = "the GitHub account whose workflow runs may use the deploy runner"
}

variable "github_connection_arn" {
  type        = string
  default     = "arn:aws:codeconnections:us-east-2:523520772490:connection/8f0cdd19-073e-4903-ae99-12228cf856e7"
  description = "the CodeConnections connection to GitHub, created and authorised in the console"
}
