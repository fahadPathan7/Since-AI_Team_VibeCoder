# Private bucket for the web page, read only by CloudFront
resource "aws_s3_bucket" "web" {
  bucket        = "${local.name}-web"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "web" {
  bucket                  = aws_s3_bucket.web.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "web" {
  bucket = aws_s3_bucket.web.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.web.arn}/*"
      Condition = { StringEquals = { "AWS:SourceArn" = aws_cloudfront_distribution.site.arn } }
    }]
  })
}

# Every file of dashboard/web, with its content type
resource "aws_s3_object" "web" {
  for_each     = local.web_files
  bucket       = aws_s3_bucket.web.id
  key          = each.value
  source       = "${local.web_dir}/${each.value}"
  etag         = filemd5("${local.web_dir}/${each.value}")
  content_type = lookup(local.mime, reverse(split(".", each.value))[0], "application/octet-stream")
}

# Private bucket for uploaded files and run results, emptied after one day
resource "aws_s3_bucket" "runs" {
  bucket        = "${local.name}-runs"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "runs" {
  bucket                  = aws_s3_bucket.runs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "runs" {
  bucket = aws_s3_bucket.runs.id
  rule {
    id     = "expire-after-one-day"
    status = "Enabled"
    filter {}
    expiration {
      days = 1
    }
  }
}

# Browsers upload directly to this bucket with a signed URL, so allow the site's origin
resource "aws_s3_bucket_cors_configuration" "runs" {
  bucket = aws_s3_bucket.runs.id
  cors_rule {
    allowed_methods = ["PUT"]
    allowed_origins = ["https://${aws_cloudfront_distribution.site.domain_name}"]
    allowed_headers = ["*"]
    max_age_seconds = 3600
  }
}
