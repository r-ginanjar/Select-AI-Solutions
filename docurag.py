import json
import re
from pathlib import Path

import gradio as gr
import oci
import oracledb
import yaml

# Declare global variables
with open('config.yaml', 'r') as file:
    data = yaml.safe_load(file)

config = oci.config.from_file()
config['region'] = data['region']
object_storage_client = oci.object_storage.ObjectStorageClient(config)

namespace = data['namespace']
bucket = data['bucket']
region = data['region']
vector_index_name = data['vector-index-name']
cred_name = data['cred-name']
ai_profile_name = data['docurag-ai-profile-name']
db_user = data['db-user']
db_cs = data['db-cs']
db_pass = data['db-pass']
db_wallet_loc = data['db-wallet-loc']

# Define functions
def delete_pdfs_in_bucket():
    """Delete all PDF files in the specified OCI bucket."""
    # list pdf files
    object_lists = object_storage_client.list_objects(namespace, bucket).data.objects
    pdf_files = [file.name for file in object_lists if file.name.endswith(".pdf")]

    # delete the files
    if len(pdf_files) > 0:
        for pdf_file in pdf_files:
            object_storage_client.delete_object(namespace, bucket, pdf_file)

def upload_pdfs(files):
    """Upload PDF files to the specified OCI bucket."""
    for file in files:
        file = Path(file)
        file_name = file.name.replace(" ","_")
    
        with open(file, 'rb') as f:
            object_storage_client.put_object(namespace, bucket, file_name, f)

def create_vector_index():
    """Create a vector index in the Oracle database."""
    # Drop vector index
    drop_index_sql = """
        BEGIN
            DBMS_CLOUD_AI.DROP_VECTOR_INDEX(
                index_name  => :ix,
                include_data => TRUE,
                force => TRUE
            );
        END;
    """
   
    bucket_location = f"https://objectstorage.{region}.oraclecloud.com/n/{namespace}/b/{bucket}/o/"

    attrs_json = json.dumps({
        "vector_db_provider": "oracle",
        "location": bucket_location,
        "object_storage_credential_name": cred_name,
        "profile_name": ai_profile_name
    }, separators=(',', ':'), ensure_ascii=False)

    create_index_sql = """
        BEGIN
            DBMS_CLOUD_AI.CREATE_VECTOR_INDEX(
                index_name  => :ix,
                attributes  => :attr_json
            );
        END;
    """

    # execute queries
    with oracledb.connect(
        user=db_user,
        password=db_pass,
        dsn=db_cs,
        config_dir=db_wallet_loc,
        wallet_location=db_wallet_loc,
        wallet_password=db_pass
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute(drop_index_sql, ix=vector_index_name)
            cursor.execute(create_index_sql, ix=vector_index_name, attr_json=attrs_json)


def handle_file(files):
    """Handle file upload and processing."""
    status = "Uploading document(s) to OCI Object Storage..."
    yield gr.update(value=status)
    delete_pdfs_in_bucket()
    upload_pdfs(files)

    status = "Document(s) uploaded. Creating vector data store..."
    yield gr.update(value=status)
    create_vector_index()

    status = "Document processing is complete. The system is ready to handle question answering."
    yield gr.update(value=status)


def escape_for_sql(text):
    """Escape single quotes in SQL queries."""
    return text.replace("'", "''")


def reformat_sources(match):
    """Reformat sources from JSON to a readable string format."""
    sources_json = match.group(1)
    try:
        sources = json.loads(sources_json)
        formatted_sources = "Sources:\n"
        for src in sources:
            formatted_sources += f"* {src['source']}: {src['url']}\n"
        return formatted_sources.strip()
    except json.JSONDecodeError:
        return match.group(0)  # fallback if JSON parsing fails

def chatbot_fn(message, history):
    """Process a chatbot message and return the response."""
    with oracledb.connect(
        user=db_user,
        password=db_pass,
        dsn=db_cs,
        config_dir=db_wallet_loc,
        wallet_location=db_wallet_loc,
        wallet_password=db_pass
    ) as conn:
        with conn.cursor() as cursor:
        
            cursor.callproc("DBMS_CLOUD_AI.SET_PROFILE", [ai_profile_name])
            message = escape_for_sql(message)
            select_ai_query = f"SELECT AI NARRATE '{message}'"
            
            try:            
                cursor.execute(select_ai_query)
            except Exception as e:
                error_message = str(e)

                cleaned = re.sub(
                    r"^ORA-20000: Sorry, unfortunately.*?\n\n",  # match until the first double newlines
                    "",
                    error_message,
                    flags=re.DOTALL
                )

                # Remove the ORA-06512 trailing part
                cleaned = re.sub(
                    r"\nORA-06512:.*$",  # match from first ORA-06512 until end
                    "",
                    cleaned,
                    flags=re.DOTALL
                )
                
                cleaned = re.sub(
                    r"Sources:\s*(\[[\s\S]*\])",  # match JSON array after 'Sources:'
                    lambda m: reformat_sources(m),
                    cleaned
                )

                return cleaned.strip()

            result = cursor.fetchone()
            answer = result[0]

    return answer

if __name__ == "__main__":

    with gr.Blocks(title="Oracle Document QA Chatbot") as demo:
        gr.Markdown("# 📑 Document QA Chatbot: Context-aware Chatbot Powered by Oracle Select AI")
        file_input = gr.Files(label="Upload PDF files", file_types=[".pdf"], height=120)
        status_label = gr.Markdown(value="Please upload a file.")
        text_box = gr.Textbox(label="Ask a question about the uploaded document(s)", placeholder="Type your question here...")
        
        # Update status_label and text_box dynamically during file handling
        file_input.upload(handle_file, inputs=file_input, outputs=[status_label])

        chat_interface = gr.ChatInterface(fn=chatbot_fn,
                                type='messages',
                                textbox=text_box,
                                show_progress='full')

    # demo.launch(share=True, show_api=False, auth=("bsi_admin", "bsi1351"))
    demo.launch(share=True, show_api=False)
