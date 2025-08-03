import gradio as gr
import oci
import yaml
from pathlib import Path
import oracledb
import json

# Declare global variables
with open('config.yaml', 'r') as file:
    data = yaml.safe_load(file)

config = oci.config.from_file()
object_storage_client = oci.object_storage.ObjectStorageClient(config)

namespace = data['namespace']
bucket = data['bucket']
region = data['region']
vector_index_name = data['vector-index-name']
cred_name = data['cred-name']
ai_profile_name = data['ai-profile-name']
db_user = data['db-user']
db_cs = data['db-cs']
db_pass = data['db-pass']
db_wallet_loc = data['db-wallet-loc']


# Define functions
def delete_pdfs_in_bucket():
    # list pdf files
    object_lists = object_storage_client.list_objects(namespace, bucket).data.objects
    pdf_files = [file.name for file in object_lists if file.name.endswith(".pdf")]

    # delete the files
    if len(pdf_files) > 0:
        for pdf_file in pdf_files:
            object_storage_client.delete_object(namespace, bucket, pdf_file)

def upload_pdfs(files):
    for file in files:
        file = Path(file)
        file_name = file.name
    
        with open(file, 'rb') as f:
            object_storage_client.put_object(namespace, bucket, file_name, f)

def create_vector_index():
    # Drop vector index
    drop_index_sql = f"""
        BEGIN
            DBMS_CLOUD_AI.DROP_VECTOR_INDEX(
                index_name  => '{vector_index_name}',
                include_data => TRUE,
                force => TRUE,
                        );
        END
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
        END
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
            cursor.execute(drop_index_sql)
            cursor.execute(create_index_sql, ix=vector_index_name, attr_json=attrs_json)


def handle_file(files):
    
    status = "Uploading document(s) to OCI Object Storage..."
    yield gr.update(value=status)
    delete_pdfs_in_bucket()
    upload_pdfs(files)

    status = "Document(s) uploaded. Creating vector data store..."
    yield gr.update(value=status)
    create_vector_index()

    status = "Document processing is complete. The system is ready to handle question answering."
    yield gr.update(value=status)



def chatbot_fn(message, history):
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
