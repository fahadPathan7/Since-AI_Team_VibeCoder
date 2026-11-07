resource "aws_cloudfront_origin_access_control" "web" {
  name                              = "${local.name}-web"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

data "aws_cloudfront_cache_policy" "optimized" {
  name = "Managed-CachingOptimized"
}

data "aws_cloudfront_cache_policy" "disabled" {
  name = "Managed-CachingDisabled"
}

# Pass query strings and body headers to the API, but not the browser's password header
resource "aws_cloudfront_origin_request_policy" "api" {
  name = "${local.name}-api"
  cookies_config {
    cookie_behavior = "none"
  }
  query_strings_config {
    query_string_behavior = "all"
  }
  headers_config {
    header_behavior = "whitelist"
    headers {
      items = ["Content-Type", "Accept", "Origin"]
    }
  }
}

# Optional password prompt for the whole site
resource "aws_cloudfront_function" "auth" {
  count   = local.use_auth ? 1 : 0
  name    = "${local.name}-auth"
  runtime = "cloudfront-js-2.0"
  publish = true
  code    = <<-JS
    function handler(event) {
      var expected = "Basic ${base64encode("${var.basic_auth_user}:${var.basic_auth_password}")}";
      var h = event.request.headers.authorization;
      if (h && h.value === expected) return event.request;
      return { statusCode: 401, statusDescription: "Unauthorized", headers: { "www-authenticate": { value: "Basic realm=\"Imbalance Price Watch\"" } } };
    }
  JS
}

# One address for the page and the API, with HTTPS from CloudFront's own certificate
resource "aws_cloudfront_distribution" "site" {
  enabled             = true
  comment             = "Imbalance Price Watch"
  default_root_object = "index.html"
  price_class         = "PriceClass_100"
  http_version        = "http2and3"

  origin {
    origin_id                = "web"
    domain_name              = aws_s3_bucket.web.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.web.id
  }

  dynamic "origin" {
    for_each = local.with_api ? [1] : []
    content {
      origin_id   = "api"
      domain_name = split("/", aws_lambda_function_url.api[0].function_url)[2]
      custom_origin_config {
        http_port              = 80
        https_port             = 443
        origin_protocol_policy = "https-only"
        origin_ssl_protocols   = ["TLSv1.2"]
        origin_read_timeout    = 60
      }
      custom_header {
        name  = "x-origin-verify"
        value = random_password.origin_secret.result
      }
    }
  }

  default_cache_behavior {
    target_origin_id       = "web"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    cache_policy_id        = data.aws_cloudfront_cache_policy.optimized.id
    compress               = true
    dynamic "function_association" {
      for_each = local.use_auth ? [1] : []
      content {
        event_type   = "viewer-request"
        function_arn = aws_cloudfront_function.auth[0].arn
      }
    }
  }

  dynamic "ordered_cache_behavior" {
    for_each = local.with_api ? [1] : []
    content {
      path_pattern             = "/api/*"
      target_origin_id         = "api"
      viewer_protocol_policy   = "redirect-to-https"
      allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
      cached_methods           = ["GET", "HEAD"]
      cache_policy_id          = data.aws_cloudfront_cache_policy.disabled.id
      origin_request_policy_id = aws_cloudfront_origin_request_policy.api.id
      compress                 = true
      dynamic "function_association" {
        for_each = local.use_auth ? [1] : []
        content {
          event_type   = "viewer-request"
          function_arn = aws_cloudfront_function.auth[0].arn
        }
      }
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}
