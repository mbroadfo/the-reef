terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Remote state — create the bucket once with:
  #   aws s3 mb s3://reef-tf-state --region us-east-1
  #   aws s3api put-bucket-versioning --bucket reef-tf-state \
  #     --versioning-configuration Status=Enabled
  # Then uncomment:
  #
  # backend "s3" {
  #   bucket = "reef-tf-state"
  #   key    = "reef-dashboard/terraform.tfstate"
  #   region = "us-east-1"
  # }
}

provider "aws" {
  region = var.aws_region
}

locals {
  app  = var.app_name
  tags = { Project = "TheReef", ManagedBy = "terraform" }
}
