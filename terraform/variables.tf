variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Project name for resource tagging"
  type        = string
  default     = "nimbuskart"
}

variable "environment" {
  description = "Environment name (staging, production)"
  type        = string
  default     = "staging"
}

variable "owner" {
  description = "Team or individual responsible for the resource"
  type        = string
  default     = "devops-team"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.20.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets"
  type        = list(string)
  default     = ["10.20.1.0/24", "10.20.2.0/24"]
}

variable "availability_zones" {
  description = "Availability zones for subnets"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

variable "ssh_cidr_blocks" {
  description = "CIDR blocks allowed SSH access. WARNING: 0.0.0.0/0 is insecure."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.micro"
}

variable "ami_id" {
  description = "AMI ID for EC2 instances"
  type        = string
    default     = "ami-979d7649"
}

variable "ebs_volume_size" {
  description = "Size in GB for the unattached EBS volume"
  type        = number
  default     = 10
}

variable "instance_count" {
  description = "Number of EC2 instances in the web tier"
  type        = number
  default     = 2
}

variable "enable_lifecycle" {
  description = "Enable S3 lifecycle expiration for noncurrent versions. Set false for LocalStack (limited support)."
  type        = bool
  default     = false
}
