resource "google_project_service" "cloud_pubsub_api" {
  service = "pubsub.googleapis.com"

  disable_dependent_services = true
  disable_on_destroy         = false
  project = var.project_id
}