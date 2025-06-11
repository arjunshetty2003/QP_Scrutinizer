from flask import Flask, render_template, request, jsonify
import json
import os

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_files():
    # Demo mode - simulate successful upload
    return jsonify({
        'success': True,
        'syllabus_docs': 12,  # Mock data
        'textbook_docs': 450,
        'question_paper_path': 'demo_mode'
    })

@app.route('/validate', methods=['POST'])
def validate_questions():
    # Demo mode - return sample validation results
    demo_results = [
        {
            "question_id": "Unit I - 1a",
            "question_text": "Define Software Engineering. Discuss the four important attributes and ethical responsibilities.",
            "syllabus_status": "IN_SYLLABUS",
            "syllabus_reasoning": "This question is covered under Unit I 'Professional software development' and 'Software engineering ethics' sections.",
            "textbook_status": "YES_IN_TEXTBOOK",
            "textbook_reasoning": "Chapter 1 of the textbook covers software engineering definitions and professional ethics in detail."
        },
        {
            "question_id": "Unit I - 1b", 
            "question_text": "Explain the working of a waterfall model with a neat diagram.",
            "syllabus_status": "IN_SYLLABUS",
            "syllabus_reasoning": "Covered under Unit I 'Software process models' section.",
            "textbook_status": "YES_IN_TEXTBOOK",
            "textbook_reasoning": "Chapter 2 section 2.1 explains waterfall model with diagrams."
        },
        {
            "question_id": "Unit II - 2a",
            "question_text": "What is advanced quantum computing in software?",
            "syllabus_status": "OUT_OF_SYLLABUS", 
            "syllabus_reasoning": "Quantum computing is not mentioned in any syllabus unit.",
            "textbook_status": "NOT_APPLICABLE",
            "textbook_reasoning": ""
        }
    ]
    
    return jsonify({'results': demo_results})

if __name__ == '__main__':
    print("🎭 QP Scrutiniser - DEMO MODE")
    print("===============================")
    print("Running without API calls to show the interface")
    print("Get a new Gemini API key to enable full functionality")
    print("")
    app.run(debug=True, port=5001)
