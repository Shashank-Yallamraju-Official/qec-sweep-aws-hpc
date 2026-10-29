terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # The state bucket is the one resource made by hand, once, because the
  # state that would describe it has nowhere to live until it exists:
  #   aws s3api create-bucket --bucket qec-sweep-tfstate-<account> --region us-east-2 \
  #     --create-bucket-configuration LocationConstraint=us-east-2
  #   aws s3api put-bucket-versioning --bucket qec-sweep-tfstate-<account> \
  #     --versioning-configuration Status=Enabled
  backend "s3" {
    bucket       = "qec-sweep-tfstate-523520772490"
    key          = "infra/terraform.tfstate"
    region       = "us-east-2"
    use_lockfile = true
  }
}
