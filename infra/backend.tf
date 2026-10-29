terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }

  # The state bucket is the one resource made by hand, once, because the
  # state that would describe it has nowhere to live until it exists.
  backend "s3" {
    bucket       = "qec-sweep-tfstate-523520772490"
    key          = "infra/terraform.tfstate"
    region       = "us-east-2"
    use_lockfile = true
  }
}
