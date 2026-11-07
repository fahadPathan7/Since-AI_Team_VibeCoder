# Role for the API function: logs, the runs bucket and starting its own background runs
resource "aws_iam_role" "api" {
  name = "${local.name}-api"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy_attachment" "logs" {
  role       = aws_iam_role.api.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "api" {
  name = "runs-and-self-invoke"
  role = aws_iam_role.api.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject"], Resource = "${aws_s3_bucket.runs.arn}/*" },
      { Effect = "Allow", Action = "lambda:InvokeFunction", Resource = "arn:aws:lambda:${var.region}:${data.aws_caller_identity.me.account_id}:function:${local.name}-api" },
    ]
  })
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${local.name}-api"
  retention_in_days = 14
}

# The API: forecasts, alerts and runs on uploaded files
resource "aws_lambda_function" "api" {
  count         = local.with_api ? 1 : 0
  function_name = "${local.name}-api"
  role          = aws_iam_role.api.arn
  package_type  = "Image"
  image_uri     = var.image_uri
  architectures = ["arm64"]
  memory_size   = var.lambda_memory_mb
  timeout       = 300
  ephemeral_storage {
    size = 2048
  }
  environment {
    variables = {
      RUNS_BUCKET   = aws_s3_bucket.runs.id
      ORIGIN_SECRET = random_password.origin_secret.result
      RUNS_DIR      = "/tmp/runs"
    }
  }
  depends_on = [aws_cloudwatch_log_group.api, aws_iam_role_policy.api, aws_iam_role_policy_attachment.logs]
}

# Background runs are started without waiting and are not retried
resource "aws_lambda_function_event_invoke_config" "api" {
  count                  = local.with_api ? 1 : 0
  function_name          = aws_lambda_function.api[0].function_name
  maximum_retry_attempts = 0
}

# Public function URL; the function refuses requests without CloudFront's secret header
resource "aws_lambda_function_url" "api" {
  count              = local.with_api ? 1 : 0
  function_name      = aws_lambda_function.api[0].function_name
  authorization_type = "NONE"
}

resource "aws_lambda_permission" "url" {
  count                  = local.with_api ? 1 : 0
  statement_id           = "FunctionUrlPublic"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.api[0].function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

resource "aws_lambda_permission" "url_invoke" {
  count                    = local.with_api ? 1 : 0
  statement_id             = "FunctionUrlInvoke"
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.api[0].function_name
  principal                = "*"
  invoked_via_function_url = true
}
