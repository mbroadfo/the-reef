output "api_url" {
  description = "Lambda API base URL — set as REEF_API_URL in GitHub Secrets"
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "s3_website_endpoint" {
  description = "S3 website origin — point Cloudflare CNAME here"
  value       = aws_s3_bucket_website_configuration.spa.website_endpoint
}

output "s3_bucket" {
  description = "S3 bucket name"
  value       = aws_s3_bucket.spa.id
}

output "lambda_function_name" {
  value = aws_lambda_function.api.function_name
}
