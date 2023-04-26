import io
import os
import json
import functions_framework
from PyPDF2 import PdfReader, PdfWriter
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


def split_pages(input_bytes, output_path):
    pdf_reader = PdfReader(io.BytesIO(input_bytes))
    pages = []
    total_pages = len(pdf_reader.pages)

    for page_num in range(total_pages):
        pdf_writer = PdfWriter()
        pdf_writer.add_page(pdf_reader.pages[page_num])
        output_file_name = '{}_page_{}.pdf'.format(
            os.path.splitext(os.path.basename(output_path))[0],
            page_num + 1
        )

        buffer = io.BytesIO()
        pdf_writer.write_stream(buffer)

        path = "output/pdf/" + output_file_name
        blob = storage_bucket.blob(path)
        blob.upload_from_string(buffer.getvalue(),
                                content_type='application/pdf')

        msg = send_to_pubsub(msg={'file': path, 'page': (page_num + 1), 'total_pages': total_pages}, topic="split-pages")
        pages.append(msg)

    return pages


@functions_framework.cloud_event
def main(cloud_event):
    """Triggered by a change to a Cloud Storage bucket.
    Args:
        event (dict): Event payload.
    """
    file_name = cloud_event.data["name"]

    if ("input/" in file_name and file_name.endswith(".pdf")):
        content = storage_bucket.get_blob(file_name).download_as_bytes()
        pages = split_pages(content, file_name)
        storage_bucket.delete_blob(file_name)
        print("Split " + file_name + " into " + str(len(pages)) + " pages")
