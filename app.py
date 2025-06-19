from flask import Flask, render_template, request, jsonify, send_file
import json
import os
import time
import re
import numpy as np
import tempfile
import io
from werkzeug.utils import secure_filename

import google.generativeai as genai
import pdfplumber
import faiss

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads'

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- Gemini API Key Setup ---
# IMPORTANT: Replace this with your new API key from https://aistudio.google.com/app/apikey
GEMINI_API_KEY = "AIzaSyB-f56OSuAI0SdtxEGWKuyT6Z4_QSxN5xU"  # <- UPDATED WITH NEW KEY
EMBEDDING_MODEL_NAME = "models/text-embedding-004"
GENERATIVE_MODEL_NAME = 'gemini-1.5-flash-latest'
LLM_CALL_DELAY_SECONDS = 2

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)
GENERATIVE_MODEL_INSTANCE = genai.GenerativeModel(GENERATIVE_MODEL_NAME)

# Global variables
syllabus_vector_store = None
textbook_vector_store = None

class SimpleDocument:
    def __init__(self, page_content, metadata=None):
        self.page_content = page_content
        self.metadata = metadata if metadata is not None else {}

def chunk_text_by_paragraphs(text, min_chunk_len=50, max_chunk_len=700):
    if not text: return []
    paragraphs = re.split(r'\n\s*\n+', text.strip())
    chunks = []
    current_chunk = ""
    for para in paragraphs:
        para = para.strip()
        if not para: continue
        if not current_chunk: current_chunk = para
        elif len(current_chunk) + len(para) + 1 <= max_chunk_len:
            current_chunk += "\n\n" + para
        else:
            if len(current_chunk) >= min_chunk_len: chunks.append(current_chunk)
            current_chunk = para
    if current_chunk and len(current_chunk) >= min_chunk_len: chunks.append(current_chunk)

    final_chunks = []
    for chunk in chunks:
        if len(chunk) > max_chunk_len:
            for i in range(0, len(chunk), max_chunk_len):
                final_chunks.append(chunk[i:i+max_chunk_len])
        elif len(chunk) >= min_chunk_len:
             final_chunks.append(chunk)
    return final_chunks

def normalize_unit_id(unit_id_str):
    if not unit_id_str: return "UNIT-UNKNOWN"
    normalized = unit_id_str.upper().replace(" ", "").replace("_", "")
    match = re.match(r"(UNIT)([IVXLCDM\d]+)", normalized)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return normalized

def load_syllabus_from_json(file_path):
    documents = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f: 
            data = json.load(f)
        course_name = data.get("course_name", "Unknown Course")
        for unit_data in data.get("units", []):
            unit_id_val = normalize_unit_id(unit_data.get("unit", "Unknown Unit"))
            unit_title_val = unit_data.get("title", "Untitled")
            syllabus_content = unit_data.get("syllabus_content", "").strip()
            if syllabus_content:
                content_chunks = chunk_text_by_paragraphs(syllabus_content, min_chunk_len=50, max_chunk_len=400)
                if not content_chunks and syllabus_content: content_chunks = [syllabus_content]
                for i, chunk_cont in enumerate(content_chunks):
                    documents.append(SimpleDocument(chunk_cont, {
                        "source_type": "syllabus", 
                        "course_name": course_name, 
                        "unit_id": unit_id_val, 
                        "unit_title": unit_title_val, 
                        "chunk_id": f"syl_chunk_{unit_id_val.replace('-', '')}_{i}"
                    }))
    except Exception as e: 
        print(f"Error loading syllabus: {e}")
    return documents

def extract_text_from_pdf_paged(pdf_path):
    pages_text_content = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text(x_tolerance=2, y_tolerance=2, layout=False)
                if text and text.strip():
                    cleaned_text = re.sub(r'\n\s*\n+', '\n\n', text.strip())
                    pages_text_content.append({"page_number": i + 1, "text": cleaned_text})
    except Exception as e: 
        print(f"Error reading PDF: {e}")
    return pages_text_content

def prepare_textbook_documents(pdf_paths_list):
    all_textbook_documents = []
    for pdf_path in pdf_paths_list:
        if not os.path.exists(pdf_path): continue
        
        pages_data = extract_text_from_pdf_paged(pdf_path)
        if not pages_data: continue

        doc_name = os.path.basename(pdf_path)
        safe_doc_name_part = re.sub(r'[^a-zA-Z0-9_-]', '_', doc_name.replace('.pdf', ''))

        full_textbook_text = "\n\n".join([page_info["text"] for page_info in pages_data])
        textbook_chunks = chunk_text_by_paragraphs(full_textbook_text, min_chunk_len=200, max_chunk_len=800)

        for i, chunk_content in enumerate(textbook_chunks):
            all_textbook_documents.append(SimpleDocument(
                chunk_content,
                {
                    "source_type": "textbook",
                    "document_name": doc_name,
                    "chunk_id": f"tb_chunk_{safe_doc_name_part}_{i}"
                }
            ))
    return all_textbook_documents

def get_gemini_embeddings(texts, task_type="RETRIEVAL_DOCUMENT"):
    if not texts: return []
    embeddings_list = []
    BATCH_SIZE = 100
    
    for i in range(0, len(texts), BATCH_SIZE):
        batch_texts = texts[i:i + BATCH_SIZE]
        valid_texts_for_api = [text for text in batch_texts if text and text.strip()]
        
        if not valid_texts_for_api:
            embeddings_list.extend([None] * len(batch_texts))
            continue
            
        try:
            result = genai.embed_content(
                model=EMBEDDING_MODEL_NAME, 
                content=valid_texts_for_api, 
                task_type=task_type
            )
            embeddings_list.extend(result['embedding'])
            time.sleep(1.0)
        except Exception as e:
            print(f"Error generating embeddings: {e}")
            embeddings_list.extend([None] * len(batch_texts))
    return embeddings_list

class SimpleVectorStoreFAISS:
    def __init__(self, documents, embeddings_list):
        self.documents = []
        self.faiss_index = None
        self.dimension = 0
        
        if not documents or not embeddings_list: return

        valid_embeddings_np_list = []
        temp_documents = []
        for i, emb in enumerate(embeddings_list):
            if i < len(documents) and emb is not None and len(emb) > 0:
                temp_documents.append(documents[i])
                valid_embeddings_np_list.append(emb)

        if not valid_embeddings_np_list:
            self.documents = temp_documents
            return
            
        self.documents = temp_documents

        try:
            embeddings_np = np.array(valid_embeddings_np_list, dtype='float32')
            self.dimension = embeddings_np.shape[1]
            self.faiss_index = faiss.IndexFlatL2(self.dimension)
            self.faiss_index.add(embeddings_np)
        except Exception as e:
            print(f"Error building FAISS index: {e}")

    def search(self, query_text, k=5):
        if not self.faiss_index or self.faiss_index.ntotal == 0:
            return []
            
        try:
            query_embedding_result = genai.embed_content(
                model=EMBEDDING_MODEL_NAME, 
                content=[query_text.strip()], 
                task_type="RETRIEVAL_QUERY"
            )
            query_embedding_vector = query_embedding_result['embedding'][0]
        except Exception as e:
            print(f"Error embedding query: {e}")
            return []

        query_np = np.array([query_embedding_vector], dtype='float32')
        actual_k = min(k, self.faiss_index.ntotal)
        
        distances, indices = self.faiss_index.search(query_np, actual_k)
        retrieved_docs = []
        
        if indices.size > 0 and indices[0].size > 0:
            for i in range(len(indices[0])):
                idx = indices[0][i]
                if idx != -1 and idx < len(self.documents):
                    retrieved_docs.append({
                        "document": self.documents[idx], 
                        "distance": float(distances[0][i])
                    })
        return retrieved_docs

def call_gemini_llm(prompt_text):
    try:
        safety_settings_config = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
        ]
        
        response = GENERATIVE_MODEL_INSTANCE.generate_content(
            prompt_text,
            safety_settings=safety_settings_config
        )
        time.sleep(LLM_CALL_DELAY_SECONDS)
        
        if not response.candidates or not response.candidates[0].content.parts:
            return "ERROR_LLM_EMPTY_RESPONSE"
        return response.text.strip()
    except Exception as e:
        error_str = str(e)
        print(f"Error during LLM call: {e}")
        
        # Handle specific API errors
        if "API key expired" in error_str or "API_KEY_INVALID" in error_str:
            return "ERROR_API_KEY_EXPIRED"
        elif "quota" in error_str.lower() or "429" in error_str:
            return "ERROR_QUOTA_EXCEEDED"
        elif "400" in error_str:
            return "ERROR_BAD_REQUEST"
        else:
            return "ERROR_LLM_CALL_GENERAL"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_files():
    global syllabus_vector_store, textbook_vector_store
    
    try:
        # Check if files are present
        if 'syllabus' not in request.files or 'question_paper' not in request.files:
            return jsonify({'error': 'Missing required files'}), 400
        
        syllabus_file = request.files['syllabus']
        question_paper_file = request.files['question_paper']
        textbook_files = request.files.getlist('textbooks')
        
        # Save files
        syllabus_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(syllabus_file.filename))
        question_paper_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(question_paper_file.filename))
        
        syllabus_file.save(syllabus_path)
        question_paper_file.save(question_paper_path)
        
        textbook_paths = []
        for textbook_file in textbook_files:
            if textbook_file.filename:
                textbook_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(textbook_file.filename))
                textbook_file.save(textbook_path)
                textbook_paths.append(textbook_path)
        
        # Process syllabus
        syllabus_docs = load_syllabus_from_json(syllabus_path)
        if syllabus_docs:
            syllabus_texts = [doc.page_content for doc in syllabus_docs]
            syllabus_embeddings = get_gemini_embeddings(syllabus_texts)
            syllabus_vector_store = SimpleVectorStoreFAISS(syllabus_docs, syllabus_embeddings)
        
        # Process textbooks
        if textbook_paths:
            textbook_docs = prepare_textbook_documents(textbook_paths)
            if textbook_docs:
                textbook_texts = [doc.page_content for doc in textbook_docs if doc.page_content.strip()]
                textbook_embeddings = get_gemini_embeddings(textbook_texts)
                textbook_vector_store = SimpleVectorStoreFAISS(textbook_docs, textbook_embeddings)
        
        return jsonify({
            'success': True,
            'syllabus_docs': len(syllabus_docs) if syllabus_docs else 0,
            'textbook_docs': len(textbook_docs) if textbook_paths and 'textbook_docs' in locals() else 0,
            'question_paper_path': question_paper_path
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/validate', methods=['POST'])
def validate_questions():
    try:
        data = request.get_json()
        question_paper_path = data.get('question_paper_path')
        
        if not question_paper_path or not os.path.exists(question_paper_path):
            return jsonify({'error': 'Question paper file not found'}), 400
        
        if not syllabus_vector_store or not syllabus_vector_store.faiss_index:
            return jsonify({'error': 'Syllabus not processed'}), 400
        
        # Load question paper
        with open(question_paper_path, 'r', encoding='utf-8') as f:
            questions = json.load(f)
        
        results = []
        
        for idx, question_entry in enumerate(questions):
            question_id = question_entry.get("question", f"Q{idx+1}")
            question_text = question_entry.get("text", "")
            
            if not question_text.strip():
                continue
            
            # Search syllabus
            syllabus_results = syllabus_vector_store.search(question_text, k=3)
            
            # Check syllabus coverage
            syllabus_context = format_retrieved_context_for_llm(syllabus_results, "Syllabus")
            syllabus_prompt = f"""You are an expert academic assistant evaluating if an exam question is covered by a given syllabus.

Question: "{question_text}"

{syllabus_context}

Based on the syllabus sections provided:
1. Is the question IN SYLLABUS or OUT OF SYLLABUS?
2. Provide brief reasoning.

Your response MUST start with "SYLLABUS_VERDICT: IN_SYLLABUS" or "SYLLABUS_VERDICT: OUT_OF_SYLLABUS".
Then provide "REASONING: " with your explanation."""

            syllabus_response = call_gemini_llm(syllabus_prompt)
            
            # Handle API errors
            if syllabus_response.startswith("ERROR_"):
                if syllabus_response == "ERROR_API_KEY_EXPIRED":
                    return jsonify({'error': 'API key expired. Please renew your Gemini API key.'}), 400
                elif syllabus_response == "ERROR_QUOTA_EXCEEDED":
                    return jsonify({'error': 'API quota exceeded. Please check your plan and billing details or try again later.'}), 429
                else:
                    return jsonify({'error': f'API error: {syllabus_response}'}), 500
            
            # Parse syllabus response
            if syllabus_response.startswith("SYLLABUS_VERDICT: IN_SYLLABUS"):
                syllabus_status = "IN_SYLLABUS"
                syllabus_reasoning = syllabus_response.split("REASONING:", 1)[1].strip() if "REASONING:" in syllabus_response else "No reasoning provided"
            elif syllabus_response.startswith("SYLLABUS_VERDICT: OUT_OF_SYLLABUS"):
                syllabus_status = "OUT_OF_SYLLABUS"
                syllabus_reasoning = syllabus_response.split("REASONING:", 1)[1].strip() if "REASONING:" in syllabus_response else "No reasoning provided"
            else:
                syllabus_status = "ERROR"
                syllabus_reasoning = "Could not parse LLM response"
            
            # Check textbook coverage if in syllabus
            textbook_status = "NOT_APPLICABLE"
            textbook_reasoning = ""
            
            if syllabus_status == "IN_SYLLABUS" and textbook_vector_store and textbook_vector_store.faiss_index:
                textbook_results = textbook_vector_store.search(question_text, k=3)
                textbook_context = format_retrieved_context_for_llm(textbook_results, "Textbook")
                
                textbook_prompt = f"""Check if this question's topic is covered in the textbook excerpts.

Question: "{question_text}"

{textbook_context}

Answer with "TEXTBOOK_COVERAGE: YES_IN_TEXTBOOK" or "TEXTBOOK_COVERAGE: NO_IN_PROVIDED_TEXTBOOK_EXCERPTS".
Then provide "REASONING: " with your explanation."""

                textbook_response = call_gemini_llm(textbook_prompt)
                
                # Handle API errors for textbook validation
                if textbook_response.startswith("ERROR_"):
                    if textbook_response == "ERROR_API_KEY_EXPIRED":
                        return jsonify({'error': 'API key expired. Please renew your Gemini API key.'}), 400
                    elif textbook_response == "ERROR_QUOTA_EXCEEDED":
                        return jsonify({'error': 'API quota exceeded. Please check your plan and billing details or try again later.'}), 429
                    else:
                        textbook_status = "ERROR"
                        textbook_reasoning = f"API error: {textbook_response}"
                elif textbook_response.startswith("TEXTBOOK_COVERAGE: YES_IN_TEXTBOOK"):
                    textbook_status = "YES_IN_TEXTBOOK"
                    textbook_reasoning = textbook_response.split("REASONING:", 1)[1].strip() if "REASONING:" in textbook_response else "No reasoning provided"
                elif textbook_response.startswith("TEXTBOOK_COVERAGE: NO_IN_PROVIDED_TEXTBOOK_EXCERPTS"):
                    textbook_status = "NO_IN_PROVIDED_TEXTBOOK_EXCERPTS"
                    textbook_reasoning = textbook_response.split("REASONING:", 1)[1].strip() if "REASONING:" in textbook_response else "No reasoning provided"
                else:
                    textbook_status = "ERROR"
                    textbook_reasoning = "Could not parse LLM response"
            
            results.append({
                "question_id": question_id,
                "question_text": question_text,
                "syllabus_status": syllabus_status,
                "syllabus_reasoning": syllabus_reasoning,
                "textbook_status": textbook_status,
                "textbook_reasoning": textbook_reasoning
            })
        
        return jsonify({'results': results})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def format_retrieved_context_for_llm(retrieved_items, source_type_name):
    if not retrieved_items: 
        return f"No relevant {source_type_name} sections found during retrieval."
    
    context_str = f"--- Relevant {source_type_name} Sections ---\n"
    for i, item in enumerate(retrieved_items):
        doc = item["document"]
        content = doc.page_content.strip()[:500]
        metadata = doc.metadata
        context_str += f"Section {i+1}: {content}...\n\n"
    
    return context_str.strip()

if __name__ == '__main__':
    app.run(debug=True, port=5002)
    