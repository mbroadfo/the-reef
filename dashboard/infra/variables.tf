variable "aws_region" {
  description = "AWS region"
  default     = "us-east-1"
}

variable "app_name" {
  description = "Resource name prefix"
  default     = "reef-dashboard"
}

variable "bucket_name" {
  description = "S3 bucket name for the SPA — must be globally unique"
  type        = string
}

variable "mongodb_uri" {
  description = "MongoDB Atlas connection string"
  type        = string
  sensitive   = true
}

variable "mongodb_db" {
  description = "Atlas database name"
  default     = "the_reef"
}
