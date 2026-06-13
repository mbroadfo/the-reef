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

output "custom_domain_url" {
  description = "Dashboard custom domain — live once Cloudflare CNAME is added"
  value       = "https://${var.custom_domain}"
}

# ── ACM DNS validation — add these to your DNS provider ──────────────────────
output "acm_validation_cname_name" {
  description = "CNAME record name to add to your DNS provider"
  value       = tolist(aws_acm_certificate.reef.domain_validation_options)[0].resource_record_name
}

output "acm_validation_cname_value" {
  description = "CNAME record value to add to your DNS provider"
  value       = tolist(aws_acm_certificate.reef.domain_validation_options)[0].resource_record_value
}
