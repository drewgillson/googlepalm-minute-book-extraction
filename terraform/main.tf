module "base" {
  source = "./modules/base"
}

module "module_pubsub" {
  source = "./modules/pubsub"
  project_id = module.base.PROJECT_ID
}

module "module_cloud_functions" {
  source = "./modules/cloud_functions"
  project_id = module.base.PROJECT_ID
  region = module.base.REGION
  bucket_name = module.base.BUCKET_NAME
  env = {
    BUCKET_NAME = module.base.BUCKET_NAME,
    PROJECT_ID = module.base.PROJECT_ID,
    REGION = module.base.REGION,
    PROJECT_NUMBER = module.base.PROJECT_NUMBER,
    OCR_PROCESSOR_ID = module.base.OCR_PROCESSOR_ID,
    OCR_PROCESSOR_VERSION = module.base.OCR_PROCESSOR_VERSION
    CLASSIFIER_PROCESSOR_ID = module.base.CLASSIFIER_PROCESSOR_ID,
    CLASSIFIER_PROCESSOR_VERSION = module.base.CLASSIFIER_PROCESSOR_VERSION
    FORM_PARSER_PROCESSOR_ID = module.base.FORM_PARSER_PROCESSOR_ID,
    FORM_PARSER_PROCESSOR_VERSION = module.base.FORM_PARSER_PROCESSOR_VERSION
  }
}