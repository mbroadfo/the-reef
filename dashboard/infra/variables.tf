variable "aws_region" {
  description = "AWS region"
  default     = "us-west-2"
}

variable "app_name" {
  description = "Resource name prefix"
  default     = "reef-dashboard"
}

variable "bucket_name" {
  description = "S3 bucket name for the SPA — must be globally unique"
  type        = string
}

variable "custom_domain" {
  description = "Custom domain for the dashboard"
  default     = "reef.broadfoot.consulting"
}

