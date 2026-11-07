output "site_url" {
  description = "Open this address in a browser"
  value       = "https://${aws_cloudfront_distribution.site.domain_name}"
}

output "api_docs_url" {
  value = "https://${aws_cloudfront_distribution.site.domain_name}/api/docs"
}

output "ecr_repository_url" {
  value = aws_ecr_repository.api.repository_url
}

output "distribution_id" {
  value = aws_cloudfront_distribution.site.id
}

output "runs_bucket" {
  value = aws_s3_bucket.runs.id
}
