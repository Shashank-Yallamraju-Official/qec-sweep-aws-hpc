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
