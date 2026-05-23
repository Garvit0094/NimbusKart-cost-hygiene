output "vpc_id" {
  description = "VPC ID"
  value       = module.network.vpc_id
}

output "subnet_ids" {
  description = "Public subnet IDs"
  value       = module.network.public_subnet_ids
}

output "bucket_name" {
  description = "S3 bucket name"
  value       = aws_s3_bucket.main.id
}

output "instance_ids" {
  description = "EC2 instance IDs"
  value       = aws_instance.web[*].id
}

output "ebs_volume_id" {
  description = "Unattached EBS volume ID (orphan detection target)"
  value       = aws_ebs_volume.unattached.id
}

output "security_group_id" {
  description = "Web tier security group ID"
  value       = aws_security_group.web.id
}
