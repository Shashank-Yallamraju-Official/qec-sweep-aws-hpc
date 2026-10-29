provider "aws" {
  region = var.region

  # Activating `project` as a cost-allocation tag is the payer's job; this
  # account sits in an AWS-managed organisation and is refused that call.
  default_tags {
    tags = {
      project = "qec-sweep"
    }
  }
}
