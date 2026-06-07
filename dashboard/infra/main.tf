terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Remote state — create once, then uncomment:
  #   aws s3 mb s3://reef-tf-state --region us-west-2 --profile terraform
  #   aws s3api put-bucket-versioning --bucket reef-tf-state \
  #     --versioning-configuration Status=Enabled --profile terraform
  #
  # backend "s3" {
  #   bucket  = "reef-tf-state"
  #   key     = "reef-dashboard/terraform.tfstate"
  #   region  = "us-west-2"
  #   profile = "terraform"
  # }
}

provider "aws" {
  region  = var.aws_region
  profile = "terraform"
}

locals {
  app  = var.app_name
  tags = { Project = "TheReef", ManagedBy = "terraform" }
}
