output "api_url" {
  description = "Lambda API base URL — set as REEF_API_URL in GitHub Secrets"
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "cloudfront_url" {
  description = "Dashboard URL"
  value       = "https://${aws_cloudfront_distribution.spa.domain_name}"
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID — set as REEF_CF_DIST_ID in GitHub Secrets"
  value       = aws_cloudfront_distribution.spa.id
}

output "s3_bucket" {
  value = aws_s3_bucket.spa.id
}

output "lambda_function_name" {
  value = aws_lambda_function.api.function_name
}
