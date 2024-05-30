import streamlit as st
import streamlit.components.v1 as components
import requests
import pandas as pd
from google.oauth2 import service_account
from google.cloud import storage
import vertexai
import json
import random
from datetime import datetime

# AUTHENTICATION FALLBACK

#st.write(st.experimental_user["email"])
#if st.experimental_user["email"] == None:
#    st.write('<h1>Hello, Audit <span style="color:#ce00a2ff;">Aficionado</span></h1>', unsafe_allow_html=True)
#    st.write("It looks like you don't have access yet.")
#    st.write("To get access to Aficionado's audit assistant that helps you write controls, audit procedures, reviews your RACMs & audit documentation, **AND** answers questions - all based on the narratives and contextually relevant documents you provide (phew, that was a lot), request access [here](https://forms.gle/jHPByXgVFBVxNq3H7).")
#    st.stop()

# TODOs

# - Maybe also move EXAMPLES to st.secrets?
# - Maybe daily (12-hour? 1-hour?) cache for the same user, workspace file set + question?
# - Ability to delete individual workspace files
# - Ability to view, preview and/or download workspace files
# - Consistent animal emojis per file per user session
# - System instructions recitation check on GCF endpoint
# - Model call to generate filename for reponse Save to Workspace sometimes produces illegal chars. ex.: \n
# - Add Google OAuth flow and new user signup flow. Then make app public

# GLOBALS

vertexai.init(project=st.secrets['GCP_GLOBALS']['project'],
              location=st.secrets['GCP_GLOBALS']['location'],
              credentials=service_account.Credentials.from_service_account_info(st.secrets["GOOGLE_APPLICATION_CREDENTIALS"]))

STORAGE_CLIENT = storage.Client()
BUCKET = STORAGE_CLIENT.bucket(st.secrets['GCP_GLOBALS']['bucket_name'])

EMOJIS = {1481: ':crab:',1482: ':lion_face:',1483: ':scorpion:',1484: ':turkey:',1485: ':unicorn_face:',1486: ':eagle:',1487: ':duck:',1488: ':bat:',1489: ':shark:',1490: ':owl:',1491: ':fox_face:',1492: ':butterfly:',1493: ':deer:',1494: ':gorilla:',1495: ':lizard:',1496: ':rhinoceros:',1497: ':shrimp:',1498: ':squid:',1499: ':giraffe_face:',1500: ':zebra_face:',1501: ':hedgehog:',1502: ':sauropod:',1503: ':t-rex:',1504: ':cricket:',1505: ':kangaroo:',1506: ':llama:',1507: ':peacock:',1508: ':hippopotamus:',1509: ':parrot:',1510: ':raccoon:',1511: ':lobster:',1512: ':mosquito:',1513: ':microbe:',1514: ':badger:',1515: ':swan:',1516: ':mammoth:',1517: ':dodo:',1518: ':sloth:',1519: ':otter:',1520: ':orangutan:',1521: ':skunk:',1522: ':flamingo:',1523: ':oyster:',1524: ':beaver:',1525: ':bison:',1526: ':seal:',1527: ':guide_dog:'}
EXAMPLES = {0: "Write a concise bulleted list of key controls based on the provided documents.",
            1: "Are there any standard process controls you DO NOT SEE covered in the provided documents?",
            2: "Based on the documents, what are 3 ways this process or its controls could be circumvented?",
            3: "Write a table of all the acronyms used in the provided documents and their definitions.",
            4: "What are all the IT systems mentioned in the provided documents?",
            5: "What is the first control in this process document? Write audit procedures to test it.",
            6: "Write a table of all the people involved in this process and briefly describe their roles.",
            7: "What is the main objective of this process?",
            8: "Based on the provided document, write a short high-level executive summary to explain the process to an audit executive.",
            9: "Briefly summarize this document.",
            10: "When was this document created and/or last updated?",
            11: "How would you describe the tone of this document? Formal? Casual? Informed? Ignorant? Explain why.",
            12: "What business risks does this process appear designed to mitigate?",
            13: "Who owns this document? Is there any contact info for them?",
            14: "Write questions I can use to confirm how this process works. Do not ask leading questions.",
            14: "If this process had an animal mascot, what would it be and why? Use emojis.",
            15: "What overrides or circumvention methods are mentioned in the documents?",
            16: "What is the most frequent term used on each page of the document?"}
EXAMPLE_FILES = ["examples/P2P Common Key Controls.pdf",
                 "examples/Cornell Purchase Order Process Narrative.pdf"]

# HELPERS

def call_cloud_function(args, endpoint):
    response = requests.get(endpoint, args)

    if response.status_code == 200:
        return response.text
    else:
       return "Error:" + str(response.status_code)


def upload_blob(source_file_name, user):
    blob = BUCKET.blob(user + '/' + source_file_name)
    blob.upload_from_filename(source_file_name)


def delete_all_blobs(username):
    blobs = STORAGE_CLIENT.list_blobs(st.secrets['GCP_GLOBALS']['bucket_name'], prefix=username)
    for blob in blobs:
        blob.delete()


def list_blobs(username):
    blobs = STORAGE_CLIENT.list_blobs(st.secrets['GCP_GLOBALS']['bucket_name'], prefix=username)
    res = []
    for blob in blobs:
        res.append(blob.name.replace(username + '/', ''))
    return res


def clone_example_blobs(username):
    for ex in EXAMPLE_FILES:
        source_blob = BUCKET.blob(ex)
        destination_blob = BUCKET.blob(username + '/' + ex.split('/')[-1])
        destination_blob.rewrite(source_blob)


# SESSION STATE

if 'username' not in st.session_state:
    st.session_state['username'] = st.experimental_user["email"].split('@')[0]
if 'workspace_files' not in st.session_state:
    st.session_state['workspace_files'] = list_blobs(st.session_state['username'])
if 'choices' not in st.session_state:
    mask = random.sample(range(len(EXAMPLES)), 3)
    st.session_state['choices'] = [EXAMPLES[mask[0]], EXAMPLES[mask[1]], EXAMPLES[mask[2]]]
if 'question' not in st.session_state:
    st.session_state['question'] = ''
if 'response' not in st.session_state:
    st.session_state['response'] = ''

def workspace_files(fnames):
    if fnames == []:
        st.session_state['workspace_files'] = fnames
    else:
        if type(fnames[0]) == str:
            st.session_state['workspace_files'].extend(fnames)
        else:
            st.session_state['workspace_files'].extend([i.name for i in fnames])
        st.session_state['workspace_files'] = list(set(st.session_state['workspace_files']))


def question(text):
    st.session_state['question'] = text


# MAIN APPLICATION FLOW

st.set_page_config(page_title='Aficionado: Your Always-On Audit Assistant',
                   page_icon='assure_ai_logo.PNG')

st.write('**This application is running on a <span style="color:red;">public cloud</span>.</br><span style="color:red;">Do not upload sensitive information</span> to your workspace.**', unsafe_allow_html=True)
st.write('<h1>Hello, Audit <span style="color:#ce00a2ff;">Aficionado</span></h1>', unsafe_allow_html=True)
st.write(f'Logged in as <span style="background-color:#fff727ff;"> **{st.session_state["username"]}** </span>', unsafe_allow_html=True)

st.markdown('**Try a Suggested Question**')
col1, col2, col3 = st.columns(3)

with col1:
    if st.button(f'###### *{st.session_state["choices"][0]}*', use_container_width=True):
        question(st.session_state["choices"][0])
with col2:
    if st.button(f'###### *{st.session_state["choices"][1]}*', use_container_width=True):
        question(st.session_state["choices"][1])
with col3:
    if st.button(f'###### *{st.session_state["choices"][2]}*', use_container_width=True):
        question(st.session_state["choices"][2])

st.markdown('**Or Ask Your Own**')
task = st.text_area(label='', label_visibility='collapsed', value=st.session_state['question'])

if st.button(label='**Submit**'):
    with st.spinner('Processing...'):
        st.session_state['response'] = call_cloud_function({"name": st.session_state['username'], 
                                                            'key': st.secrets['GCF_API_KEY'], 
                                                            'task': task
                                                           }, st.secrets['GCF_ENDPOINTS']['call_model'])

if st.session_state['response'] != "":
    with st.container(border=True):
        model_response = st.session_state['response'].replace('$', '\$')
        st.write(model_response)
        st.write('\n')
        
        col_dl_btns1, col_dl_btns2 = st.columns(2)
        
        with col_dl_btns1:
            if st.button(label='**Save to Workspace**', use_container_width=True):
                test = call_cloud_function({"name": st.session_state['username'], 
                                            'key': st.secrets['GCF_API_KEY'], 
                                            'task': f"Produce a short filename without extension for a file that contains this: {model_response}"
                                           }, st.secrets['GCF_ENDPOINTS']['call_model'])
                filename = f'{datetime.now().strftime("%Y-%m-%d %H:%M")} {test}.txt'
                with open(filename, 'w') as f:
                    f.write(model_response)
                upload_blob(filename, st.session_state['username'])
                workspace_files([filename])
                st.rerun()
                
        with col_dl_btns2:
            st.download_button("**Download**", model_response, use_container_width=True)
            
# SIDEBAR FLOW

with st.sidebar:
    with st.container(border=True):
        st.write('**Desktop Files**\n\nUpload files from your computer here. They will not be moved to your workspace until you click **Save to Workspace** below.')
        uploaded_files = st.file_uploader(label='Upload Relevant Documents',
                                        label_visibility ='collapsed',
                                        accept_multiple_files=True,
                                        type=['pdf', 'csv', 'txt'])
    for i in uploaded_files:
        with open(i.name, 'wb') as f:
            f.write(i.getvalue())
    
    if st.button(label='**Save to Workspace**', key='btn_save_files', use_container_width=True, on_click=workspace_files(uploaded_files)):
        for i in uploaded_files:
            upload_blob(i.name, st.session_state['username'])
    
    with st.container(border=True):
        st.write("**Workspace Files**\n\nThese files have been uploaded to your Workspace and will inform Aficionado's responses.")
        for f in list_blobs(st.session_state['username']):
            st.markdown(f'##### {EMOJIS[random.randint(1481, 1526)]} {f}\n')
    
    tmp = st.button(label='**Download Workspace Files**', use_container_width=True)

    if st.button(label='**Delete Workspace Files**', use_container_width=True, on_click=workspace_files([])):
        delete_all_blobs(st.session_state['username'])
        st.rerun()

    if st.button(label='**Clone Example Files into Workspace**', use_container_width=True, on_click=workspace_files(EXAMPLE_FILES)):
        clone_example_blobs(st.session_state['username'])
        st.rerun()
    
    
        
        
st.write('\n\n')

with st.expander(label='Privacy Policy'):
    components.html(open('pages/privacy.html', 'r').read(), height=500, scrolling=True)

    

## add popover privacy policy

