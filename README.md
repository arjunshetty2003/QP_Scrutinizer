# QP Scrutiniser

A Flask web application that validates question papers against syllabus and textbooks using Gemini AI.

## Features

- **Modern Web Interface**: Clean, responsive design with gradient backgrounds and smooth animations
- **File Upload**: Support for syllabus JSON, question paper JSON, and multiple textbook PDFs
- **Real-time Processing**: Shows upload and validation progress
- **Comprehensive Results**: Displays syllabus coverage, textbook coverage, and detailed reasoning
- **Filtering**: Filter results by syllabus status
- **Download Results**: Export validation results as JSON
- **Error Handling**: Proper error messages and loading states
- **Mobile Responsive**: Works well on desktop and mobile devices

## Setup Instructions

1. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the application:**
   ```bash
   python app.py
   ```

3. **Access the application:**
   Open your browser and go to `http://localhost:5000`

## File Structure

```
QP_Scrutiniser/
├── app.py                 # Flask backend application
├── requirements.txt       # Python dependencies
├── uploads/              # Directory for uploaded files
├── templates/
│   └── index.html        # Main HTML template
└── static/
    ├── css/
    │   └── style.css     # Stylesheet
    └── js/
        └── app.js        # JavaScript application logic
```

## Usage

1. **Upload Files**:
   - Syllabus JSON file (required)
   - Question Paper JSON file (required)
   - Textbook PDF files (optional, multiple files supported)

2. **Process Files**: 
   - Click "Upload and Process Files" to upload and create vector embeddings

3. **Start Validation**:
   - Click "Start Validation" to analyze questions against syllabus and textbooks

4. **View Results**:
   - See summary statistics
   - Filter results by status
   - Download results as JSON

## File Formats

### Syllabus JSON Format
```json
{
  "course_name": "Operating Systems",
  "units": [
    {
      "unit": "Unit I",
      "title": "Introduction to Operating Systems",
      "syllabus_content": "Operating System overview, system structures..."
    }
  ]
}
```

### Question Paper JSON Format
```json
[
  {
    "question": "Unit I - 1a",
    "text": "Explain the concept of system calls in operating systems."
  },
  {
    "question": "Unit I - 1b", 
    "text": "What is the difference between kernel mode and user mode?"
  }
]
```

## API Endpoints

- `GET /` - Main application page
- `POST /upload` - Upload and process files
- `POST /validate` - Validate questions against syllabus/textbooks

## Dependencies

- Flask: Web framework
- google-generativeai: Gemini AI API
- pdfplumber: PDF text extraction
- faiss-cpu: Vector similarity search
- numpy: Numerical computations
- Werkzeug: WSGI utilities
