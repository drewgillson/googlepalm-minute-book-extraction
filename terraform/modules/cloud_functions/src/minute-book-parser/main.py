import re
import functions_framework
import json
import os
import tiktoken
from langchain.prompts import PromptTemplate
from langchain.llms import VertexAI
from langchain.chains import LLMChain
from google.cloud import storage
import concurrent.futures
import entity_details
import officers
import quorum_rules
import directors
import restrictions_provisions
import share_classes


storage_client = storage.Client()
storage_bucket = storage_client.get_bucket(os.environ.get('BUCKET_NAME'))


@functions_framework.cloud_event
def main(cloud_event):
    import base64
    encoded_payload = cloud_event.data["message"]["data"]
    msg = json.loads(base64.b64decode(encoded_payload).decode())
    prefix = msg['prefix']
    print("Received message to parse: " + prefix)

    sorted_files = get_sorted_pages(prefix)

    def write_output(prefix, suffix, content):
        """
        Writes temporary output to the Google Cloud Storage bucket, to be concatenated later

        Args:
            prefix (str): The prefix for the output file path, in the form "output/txt/<filename>".
            suffix (str): The suffix for the output file name, which will be appended to the filename in the form "<filename>_<suffix>.json".
            content (Any): The content to write to the output file.
        """
        path = prefix.replace("output/txt/", "temp/") + "_" + suffix + ".json"
        blob = storage_bucket.blob(path)

        output = json.dumps(content, indent=4)
        blob.upload_from_string(output, content_type="text/json")

    def call_write_output(*args, **kwargs):
        """
        A helper function used by ThreadPoolExecutor to call write_output with the 
        given arguments and run each write_output call in a separate thread concurrently
        """
        write_output(*args, **kwargs)

    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [
            executor.submit(call_write_output, prefix=prefix, suffix="entity_details", content=entity_details.Parser(sorted_files)),
            executor.submit(call_write_output, prefix=prefix, suffix="quorum_rules", content=quorum_rules.Parser(sorted_files)),
            executor.submit(call_write_output, prefix=prefix, suffix="share_classes", content=share_classes.Parser(sorted_files)),
            executor.submit(call_write_output, prefix=prefix, suffix="directors", content=directors.Parser(sorted_files)),
            executor.submit(call_write_output, prefix=prefix, suffix="officers", content=officers.Parser(sorted_files)),
            executor.submit(call_write_output, prefix=prefix, suffix="restrictions_provisions", content=restrictions_provisions.Parser(sorted_files))
        ]

        concurrent.futures.wait(futures)

    temp_prefix = prefix.replace("output/txt/", "temp/")
    concatenate_output(temp_prefix)
    batch_delete_files(prefix)


# The following shared helper functions are called by the modules corresponding to each section of the minute book:


def num_tokens_from_string(string, encoding_name="cl100k_base"):
    """
    Returns the number of tokens in a text string.

    Args:
    - string (str): A string representing the text whose number of tokens is to be calculated.
    - encoding_name (str): A string representing the name of the encoding to use. Default is "cl100k_base".

    Returns:
    - An integer representing the number of tokens in the given text string.
    """

    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(string))
    return num_tokens


def get_url(filename):
    """
    Returns a URL that can be used to access a PDF file in a Google Cloud Storage bucket,
    given the filename of a corresponding text file.

    Args:
        filename (str): The name of the text file in the bucket, without the .txt extension.

    Returns:
        str: A URL that can be used to access the corresponding PDF file in the same bucket.
    """

    import urllib.parse
    pdf_filename = filename.replace(".txt", ".pdf").replace("output/txt/", "output/pdf/")
    encoded_filename = urllib.parse.quote(pdf_filename)
    filename = pdf_filename.replace("output/pdf/", "")
    return 'https://storage.cloud.google.com/' + os.environ.get('BUCKET_NAME') + '/' + encoded_filename


def get_page(filename):
    """
    Retrieves the contents of a file from Google Cloud Storage bucket, and returns it as a string.

    Args:
    - filename (str): A string representing the name of the file to retrieve.

    Returns:
    - A string representing the contents of the specified file.
    """

    page = storage_bucket.get_blob(filename).download_as_string()
    return page.decode("utf-8").replace(r"\n", "\n")


def get_sorted_pages(prefix):
    """
    Returns a list of tuples representing all blobs in a Google Storage Bucket whose names begin with prefix.

    Args:
    - prefix (str): A string representing the prefix to search for.

    Returns:
    - A list of tuples representing the pages that match the given prefix. Each tuple has an integer and a string value,
      where the integer represents the page number and the string represents the name of the file that contains the page.
    """

    blobs = storage_bucket.list_blobs(prefix=prefix)
    files = {}
    for blob in blobs:
        key = int(blob.name.split('_')[-1].split('.')[0])
        files.update({key: blob.name})

    pages = sorted(files.items())
    return pages


def concatenate_output(prefix):
    """
    Concatenates the contents of all temporary blobs in the Google Cloud Storage bucket
    with a specified prefix and uploads the result to a final blob in the same bucket.
    Also deletes temporary files.

    Args:
        prefix (str): The prefix to use when searching for blobs to concatenate.
    """

    blobs = storage_bucket.list_blobs(prefix=prefix)
    output = ""
    for blob in blobs:
        output += storage_bucket.get_blob(blob.name).download_as_string().decode("utf-8") + "\n"

    path = prefix.replace("temp/", "output/final/") + ".json"
    blob = storage_bucket.blob(path)
    blob.upload_from_string(output, content_type="text/json")

    batch_delete_files(prefix)


def batch_delete_files(prefix):
    """
    Deletes all files in the Google Cloud Storage bucket that have names starting with the given prefix.

    Args:
    - prefix (str): A string representing the prefix used to filter the files to be deleted.
    """

    blobs_to_delete = storage_bucket.list_blobs(prefix=prefix)

    for blob in blobs_to_delete:
        blob.delete()


def extract_address_for_person(person, sorted_files):
    """
    Extracts the mailing address of a person from a list of sorted files.

    Args:
    - person (str): A string representing a person's name.
    - sorted_files (List[Tuple[int, str]]): A list of tuples, where each tuple contains a page number and a file name.

    Returns:
    - A string representing the mailing address of the person, if found. Returns None otherwise.
    """

    for file in sorted_files:
        page_number, file_name = file
        content = get_page(file_name).lower()

        if person.lower() in content and ("address" in content 
                                            or re.findall(r"\s*[A-Za-z]\d[A-Za-z] \d[A-Za-z]\d\s*", content)  # postal codes
                                            or re.findall(r"\s*\d\d\d\d\d\s*", content)):  # zip codes

            if " " in person:
                reverse_name = " also known as " + person.split(" ")[1] + ", " + person.split(" ")[0]
            else:
                reverse_name = ""

            prompt = PromptTemplate(
                input_variables=["person", "reverse_name", "content"],
                template="""Extract the mailing address of {person}
                            {reverse_name} from this passage. The address for {person} will be found close
                            to their name. If an address is found in the passage, but is not next to {person}'s
                            name, it is likely not the correct address and you should return Not Found.
                            A mailing address must contain street, city, state/province, and zip/postal code.
                            Do not include the name in the address.
                            If the passage does not contain a mailing address at all, output Not Found.
                            Passage:
                            {content}
                            Address:""")

            chain = LLMChain(llm=VertexAI(model_name="text-bison", temperature=0.5,
                                          max_output_tokens=512),
                             prompt=prompt)

            address = chain.predict(person=person, reverse_name=reverse_name, content=content)

            if address != 'Not Found':
                return re.sub(r'\s+', ' ', address).upper()
