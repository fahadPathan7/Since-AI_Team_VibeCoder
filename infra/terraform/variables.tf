variable "region" {
  description = "AWS region for S3, Lambda and ECR. CloudFront is global."
  type        = string
  default     = "eu-north-1"
}

variable "project" {
  description = "Name prefix for every resource"
  type        = string
  default     = "imbalance-watch"
}

variable "image_uri" {
  description = "API container image in ECR, set by deploy.sh. Leave empty on the first apply, which only creates the ECR repository."
  type        = string
  default     = ""
}

variable "basic_auth_user" {
  description = "Optional user name for a browser password prompt on the whole site"
  type        = string
  default     = ""
}

variable "basic_auth_password" {
  description = "Optional password for the browser prompt. Leave empty for an open site."
  type        = string
  default     = ""
  sensitive   = true
}

variable "lambda_memory_mb" {
  description = "Memory for the API function. More memory also gives more CPU."
  type        = number
  default     = 3008
}
