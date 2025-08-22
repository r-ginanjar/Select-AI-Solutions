import yaml

import gradio as gr
import oracledb

# Declare global variables
with open('config.yaml', 'r') as file:
    data = yaml.safe_load(file)

ai_profile_name = data['chatdb-ai-profile-name']
db_user = data['db-user']
db_cs = data['db-cs']
db_pass = data['db-pass']
db_wallet_loc = data['db-wallet-loc']


def escape_for_sql(text):
    """Escape single quotes in SQL queries."""
    return text.replace("'", "''")

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
            
            cursor.execute(select_ai_query)
            result = cursor.fetchone()
            
            if isinstance(result[0], str):
                answer = result[0]
            else:
                answer = result[0].read()

    return answer

demo = gr.ChatInterface(fn=chatbot_fn, type="messages", title="ChatDB: Oracle-Powered Natural Language Interaction with your Database" )
demo.launch(share=True)
