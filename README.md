# Summary 
This Google Cloud solution uses Document AI Custom Document Classifier, OCR Processor, Form Parser, and the Google PaLM API to extract information from corporate minute books: details about the corporate entity, directors and officers, and clauses from the shareholder's agreement like quorum rules, restrictions or provisions, and share classes.

# Solution Overview
* Splits each page from a multi-page PDF into individual pages and saves PDFs to Cloud Storage
* Classifies pages using a Custom Document Classifier trained to distinguish types `dense-ocr`, `form-parser`, `certificate`, or `other`
* Parallelizes text extraction with Cloud Function instances that invoke Document AI Processors based on the page type
* Augments OCR text with  output returned from the Document AI Form Parser processor for `form-parser` pages
* Steps through each page of OCR text to collect relevant entities into the extraction schema using heuristics and LLM prompts
* Writes structured JSON output with entitities of interest to Cloud Storage

# Requirements
* Google Cloud project with a Cloud Storage bucket, Document AI OCR Processor, Form Parser, and Custom Document Classifier 
* Terraform v1.4.5 to deploy Cloud Functions, Pub/Sub queues
  * Update terraform/modules/base/outputs.tf with your own instance IDs