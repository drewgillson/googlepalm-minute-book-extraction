variable "bucket_name" {
  type = string
}

variable "region" {
  type = string
}

variable "description" {
  type = string
  default = "Cloud function managed by Terraform"
}

variable "project_id" {
  type = string
}

variable "labels" {
  type = map(string)
  default = {}
}

variable "runtime" {
  description = "The runtime in which to run the function. Required when deploying a new function, optional when updating an existing function."
  type = string
  default = "python39"
}

variable "entry_point" {
  type = string
  default = "main"
}

variable "env" {
  type = map(string)
  default = {}
}

variable "excludes" {
  description = "Files to exclude from the src/ directory"
  type = list(string)
  default = []
}