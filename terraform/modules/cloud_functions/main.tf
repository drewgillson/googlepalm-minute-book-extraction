resource "google_project_service" "compute_engine_api" {
  service = "compute.googleapis.com"

  disable_dependent_services = true
  disable_on_destroy = false
  project = var.project_id
}

resource "google_project_service" "cloud_functions_api" {
  service = "cloudfunctions.googleapis.com"

  disable_dependent_services = true
  disable_on_destroy = false
  project = var.project_id
}

resource "google_project_service" "cloud_artifactregistry_api" {
  service = "artifactregistry.googleapis.com"

  disable_dependent_services = true
  disable_on_destroy = false
  project = var.project_id
}

resource "google_project_service" "cloud_cloudbuild_api" {
  service = "cloudbuild.googleapis.com"

  disable_dependent_services = true
  disable_on_destroy = false
  project = var.project_id
}

resource "google_project_service" "cloud_eventarc_api" {
  service = "eventarc.googleapis.com"

  disable_dependent_services = true
  disable_on_destroy = false
  project = var.project_id
}

resource "google_project_service" "cloud_secret_manager_api" {
  service = "secretmanager.googleapis.com"

  disable_dependent_services = true
  disable_on_destroy         = false
  project = var.project_id
}

# Wait for API dependencies
resource "time_sleep" "wait_until_ready" {
  create_duration = "60s"
  depends_on = [google_project_service.cloud_eventarc_api]
}

data "google_storage_bucket" "this" {
  name = var.bucket_name
  depends_on = [
    time_sleep.wait_until_ready
  ]
}

resource "google_pubsub_topic" "split-pages" {
  name = "split-pages"
  project = var.project_id
}

resource "google_pubsub_topic" "parse-minute-book" {
  name = "parse-minute-book"
  project = var.project_id
}

resource "google_cloudfunctions2_function" "page-processor" {
  name = "page-processor"
  location = var.region
  description = var.description
  project = var.project_id
  labels = var.labels

  build_config {
    runtime = var.runtime
    entry_point = var.entry_point

    source {
      storage_source {
        bucket = data.google_storage_bucket.this.id
        object = google_storage_bucket_object.page-processor-file.name
      }
    }
  }

  service_config {
    min_instance_count = 1
    max_instance_count = 5
    timeout_seconds = 540
    available_memory    = "512M"
    environment_variables = merge({"VERSION": 1}, var.env)
    ingress_settings = "ALLOW_INTERNAL_ONLY"
    all_traffic_on_latest_revision = true
  }

  event_trigger {
    trigger_region = var.region
    event_type     = "google.cloud.pubsub.topic.v1.messagePublished"
    pubsub_topic   = google_pubsub_topic.split-pages.id
    retry_policy   = "RETRY_POLICY_DO_NOT_RETRY"
  }

  depends_on = [
    google_pubsub_topic.split-pages,
    google_storage_bucket_object.page-processor-file,
    time_sleep.wait_until_ready
  ]
}

data "archive_file" "page-processor-file" {
  type = "zip"
  output_path = "/tmp/page-processor.zip"
  source_dir = "${path.module}/src/page-processor"
  excludes = var.excludes
}

resource "google_storage_bucket_object" "page-processor-file" {
  name = "${path.module}/src/page-processor.${data.archive_file.page-processor-file.output_sha}.zip"
  bucket = data.google_storage_bucket.this.id
  source = data.archive_file.page-processor-file.output_path
  depends_on = [
    data.google_storage_bucket.this,
  ]
}

data "google_storage_project_service_account" "gcs_account" {
  project = var.project_id
}

# Service account requires the Pub/Sub Publisher(roles/pubsub.publisher) IAM role in the specified project to use CloudEvent triggers
resource "google_project_iam_member" "gcs-pubsub-publishing" {
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${data.google_storage_project_service_account.gcs_account.email_address}"
}

resource "google_service_account" "account" {
  account_id   = "gcf-sa"
  display_name = "Cloud Functions Service Account (needed for GCS events)"
  project = var.project_id
}

resource "google_project_iam_member" "invoking" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.account.email}"
  depends_on = [google_service_account.account]
}

resource "google_project_iam_member" "event-receiving" {
  project = var.project_id
  role    = "roles/eventarc.eventReceiver"
  member  = "serviceAccount:${google_service_account.account.email}"
  depends_on = [google_service_account.account]
}

resource "google_project_iam_member" "artifactregistry-reader" {
  project = var.project_id
  role     = "roles/artifactregistry.reader"
  member   = "serviceAccount:${google_service_account.account.email}"
  depends_on = [google_service_account.account]
}

resource "google_project_iam_member" "storage-object-admin" {
  project = var.project_id
  role = "roles/storage.objectAdmin"
  member   = "serviceAccount:${google_service_account.account.email}"
  depends_on = [google_service_account.account]
}

resource "google_project_iam_member" "storage-admin" {
  project = var.project_id
  role = "roles/storage.admin"
  member   = "serviceAccount:${google_service_account.account.email}"
  depends_on = [google_service_account.account]
}

resource "google_project_iam_member" "pubsub-publisher" {
  project = var.project_id
  role = "roles/pubsub.publisher"
  member   = "serviceAccount:${google_service_account.account.email}"
  depends_on = [google_service_account.account]
}

resource "google_project_iam_member" "pubsub-subscriber" {
  project = var.project_id
  role = "roles/pubsub.subscriber"
  member   = "serviceAccount:${google_service_account.account.email}"
  depends_on = [google_service_account.account]
}

resource "google_project_iam_member" "secret-accessor" {
  project = var.project_id
  role = "roles/secretmanager.secretAccessor"
  member   = "serviceAccount:${google_service_account.account.email}"
  depends_on = [google_service_account.account]
}

resource "google_cloudfunctions2_function" "input-listener" {
  name = "input-listener"
  location = var.region
  description = var.description
  project = var.project_id

  build_config {
    runtime     = var.runtime
    entry_point = var.entry_point

    source {
      storage_source {
        bucket = data.google_storage_bucket.this.id
        object = google_storage_bucket_object.input-listener-file.name
      }
    }
  }

  service_config {
    min_instance_count = 1
    max_instance_count  = 3
    available_memory    = "512M"
    timeout_seconds     = 540
    environment_variables = merge({"VERSION": 1}, var.env)
    ingress_settings = "ALLOW_INTERNAL_ONLY"
    all_traffic_on_latest_revision = true
    service_account_email = google_service_account.account.email
  }

  event_trigger {
    trigger_region = lower(data.google_storage_bucket.this.location)
    event_type = "google.cloud.storage.object.v1.finalized"
    retry_policy = "RETRY_POLICY_DO_NOT_RETRY"
    service_account_email = google_service_account.account.email
    event_filters {
      attribute = "bucket"
      value = data.google_storage_bucket.this.name
    }
  }

  depends_on = [
    google_project_iam_member.event-receiving,
    google_project_iam_member.artifactregistry-reader,
    google_storage_bucket_object.input-listener-file,
    time_sleep.wait_until_ready
  ]
}

data "archive_file" "input-listener-file" {
  type = "zip"
  output_path = "/tmp/input-listener.zip"
  source_dir = "${path.module}/src/input-listener"
  excludes = var.excludes
}

resource "google_storage_bucket_object" "input-listener-file" {
  name = "${path.module}/src/input-listener.${data.archive_file.input-listener-file.output_sha}.zip"
  bucket = data.google_storage_bucket.this.id
  source = data.archive_file.input-listener-file.output_path
  depends_on = [
    data.google_storage_bucket.this,
  ]
}

// TODO: you must define the value for this secret in the Google Cloud Console
resource "google_secret_manager_secret" "secret-google-api-key" {
  secret_id = "GOOGLE_API_KEY"
  project = var.project_id

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

resource "google_cloudfunctions2_function" "minute-book-parser" {
  name = "minute-book-parser"
  location = var.region
  description = var.description
  project = var.project_id

  build_config {
    runtime     = var.runtime
    entry_point = var.entry_point

    source {
      storage_source {
        bucket = data.google_storage_bucket.this.id
        object = google_storage_bucket_object.minute-book-parser-file.name
      }
    }
  }

  service_config {
    min_instance_count = 1
    max_instance_count  = 5
    available_memory    = "512M"
    timeout_seconds     = 3600
    environment_variables = merge({"VERSION": 1}, var.env)
    ingress_settings = "ALLOW_INTERNAL_ONLY"
    all_traffic_on_latest_revision = true
    service_account_email = google_service_account.account.email

    secret_environment_variables {
      key = "GOOGLE_API_KEY"
      project_id = var.project_id
      secret = google_secret_manager_secret.secret-google-api-key.secret_id
      version = "latest"
    }
  }

  event_trigger {
    trigger_region = var.region
    event_type     = "google.cloud.pubsub.topic.v1.messagePublished"
    pubsub_topic   = google_pubsub_topic.parse-minute-book.id
    retry_policy   = "RETRY_POLICY_DO_NOT_RETRY"
  }

  depends_on = [
    google_pubsub_topic.parse-minute-book,
    google_storage_bucket_object.minute-book-parser-file,
    time_sleep.wait_until_ready
  ]
}

data "archive_file" "minute-book-parser-file" {
  type = "zip"
  output_path = "/tmp/minute-book-parser.zip"
  source_dir = "${path.module}/src/minute-book-parser"
  excludes = var.excludes
}

resource "google_storage_bucket_object" "minute-book-parser-file" {
  name = "${path.module}/src/minute-book-parser.${data.archive_file.minute-book-parser-file.output_sha}.zip"
  bucket = data.google_storage_bucket.this.id
  source = data.archive_file.minute-book-parser-file.output_path
  depends_on = [
    data.google_storage_bucket.this,
  ]
}