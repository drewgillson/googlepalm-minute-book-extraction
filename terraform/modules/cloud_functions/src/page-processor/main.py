import base64
import functions_framework
import json
import os
import re
from google.api_core.client_options import ClientOptions
from google.cloud import documentai_v1 as documentai
from google.cloud import storage
from google.cloud import pubsub_v1

storage_client = storage.Client()
storage_bucket = storage_client.get_bucket(os.environ.get('BUCKET_NAME'))
publisher = pubsub_v1.PublisherClient()
project_number = os.environ.get("PROJECT_NUMBER")


def send_to_pubsub(msg, topic):
    topic = publisher.topic_path(project_number, topic)
    if publisher.publish(topic, data=json.dumps(msg).encode("utf-8")):
        return msg


@functions_framework.cloud_event
def main(cloud_event):
    encoded_payload = cloud_event.data["message"]["data"]
    msg = json.loads(base64.b64decode(encoded_payload).decode())
    # The schema of the message is defined in helpers.send_to_pubsub()
    file = msg['file']

    region_two_char = os.environ.get('REGION')[:2]

    if file.endswith(".pdf"):
        blob = storage_bucket.get_blob(file)
        content = blob.download_as_string() if blob else None
        tables = ""

        if content:
            classifier_result = process_document(
                project_id=os.environ.get('PROJECT_ID'),
                location=region_two_char,
                processor_id=os.environ.get('CLASSIFIER_PROCESSOR_ID'),
                processor_version=os.environ.get('CLASSIFIER_PROCESSOR_VERSION'),
                content=content
            )

            page_class = ""
            if classifier_result.document:
                entities = classifier_result.document.entities
                # Sort the list by the "confidence" key in descending order
                sorted_data = sorted(entities, key=lambda x: x.confidence, reverse=True)
                if len(sorted_data) > 0:
                    highest_confidence_item = sorted_data[0]
                    page_class = highest_confidence_item.type_

            if page_class in ["dense-ocr", "other", "certificate"]:
                parser_result = process_document(
                    project_id=os.environ.get('PROJECT_ID'),
                    location=region_two_char,
                    processor_id=os.environ.get('OCR_PROCESSOR_ID'),
                    processor_version=os.environ.get('OCR_PROCESSOR_VERSION'),
                    content=content
                )
            elif page_class == "form-parser":
                parser_result = process_document(
                    project_id=os.environ.get('PROJECT_ID'),
                    location=region_two_char,
                    processor_id=os.environ.get('FORM_PARSER_PROCESSOR_ID'),
                    processor_version=os.environ.get('FORM_PARSER_PROCESSOR_VERSION'),
                    content=content
                )
                tables = tables_to_csv(parser_result.document)

            if parser_result:
                doc = parser_result.document
                output = doc.text
                if tables:
                    output += tables

                new_path = file.replace("output/pdf/", "output/txt/").replace(".pdf", ".txt")
                blob = storage_bucket.blob(new_path)

                # Save OCR text and tables (expressed as CSV) back to Cloud Storage
                blob.upload_from_string(output)
                print(f"Uploaded {new_path}")

    total_pages = msg['total_pages']
    prefix = re.sub(r"_page_\d+\.txt", "", new_path)
    blobs = storage_bucket.list_blobs(prefix=prefix)
    blob_count = sum(1 for _ in blobs)

    if (blobs and total_pages == blob_count):
        # Send a message to the pubsub topic to start the next stage of the pipeline
        print(f"Sending message to parse-minute-book topic: {prefix}")
        send_to_pubsub(msg={"prefix": prefix}, topic="parse-minute-book")


def process_document(
    project_id: str,
    location: str,
    processor_id: str,
    processor_version: str,
    content: str
) -> documentai.Document:

    if len(content) > 0:
        opts = ClientOptions(api_endpoint=f"{location}-documentai.googleapis.com")
        client = documentai.DocumentProcessorServiceClient(client_options=opts)

        processor = client.processor_version_path(
            project_id, location, processor_id, processor_version
        )

        input = documentai.RawDocument(content=content, mime_type="application/pdf")
        request = documentai.ProcessRequest(name=processor, raw_document=input)
        result = client.process_document(request)

        return result


def tables_to_csv(doc: documentai.Document) -> str:
    from google.cloud.documentai_toolbox import document
    wrapped_document = document.Document.from_documentai_document(doc)

    output = ""
    for page_number, page in enumerate(wrapped_document.pages):
        for table_number, table in enumerate(page.tables):
            output = "Comma-Separated Values Table\n===\n"
            output += wrapped_document.pages[page_number].tables[table_number].to_csv()

    return output
