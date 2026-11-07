provider "aws" {
  region = var.region
  default_tags {
    tags = { Project = var.project }
  }
}

data "aws_caller_identity" "me" {}

locals {
  name     = "${var.project}-${random_id.suffix.hex}"
  web_dir  = "${path.module}/../../dashboard/web"
  with_api = var.image_uri != ""
  use_auth = var.basic_auth_password != ""
  mime = {
    html = "text/html; charset=utf-8", css = "text/css; charset=utf-8", js = "text/javascript; charset=utf-8",
    json = "application/json", svg = "image/svg+xml", png = "image/png", ico = "image/x-icon", txt = "text/plain"
  }
  web_files = { for f in fileset(local.web_dir, "**") : f => f if !startswith(f, ".") }
}

resource "random_id" "suffix" {
  byte_length = 3
}

resource "random_password" "origin_secret" {
  length  = 40
  special = false
}

# Container registry for the API image
resource "aws_ecr_repository" "api" {
  name                 = "${var.project}-api"
  image_tag_mutability = "MUTABLE"
  force_delete         = true
}

resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.api.name
  policy = jsonencode({
    rules = [{ rulePriority = 1, description = "Keep the last 5 images", selection = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 5 }, action = { type = "expire" } }]
  })
}
