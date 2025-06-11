class QPScrutiniser {
    constructor() {
        this.validationResults = [];
        this.questionPaperPath = null;
        this.initializeEventListeners();
    }

    initializeEventListeners() {
        const uploadForm = document.getElementById('uploadForm');
        const validateBtn = document.getElementById('validateBtn');
        const statusFilter = document.getElementById('statusFilter');
        const downloadBtn = document.getElementById('downloadBtn');

        uploadForm.addEventListener('submit', (e) => this.handleFileUpload(e));
        validateBtn.addEventListener('click', () => this.startValidation());
        statusFilter.addEventListener('change', (e) => this.filterResults(e.target.value));
        downloadBtn.addEventListener('click', () => this.downloadResults());
    }

    async handleFileUpload(event) {
        event.preventDefault();
        
        const formData = new FormData();
        const syllabusFile = document.getElementById('syllabus').files[0];
        const questionPaperFile = document.getElementById('question_paper').files[0];
        const textbookFiles = document.getElementById('textbooks').files;

        if (!syllabusFile || !questionPaperFile) {
            this.showError('Please select both syllabus and question paper files.');
            return;
        }

        formData.append('syllabus', syllabusFile);
        formData.append('question_paper', questionPaperFile);
        
        for (let i = 0; i < textbookFiles.length; i++) {
            formData.append('textbooks', textbookFiles[i]);
        }

        this.showUploadStatus('Uploading and processing files...', 'loading');

        try {
            const response = await fetch('/upload', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            if (response.ok) {
                this.questionPaperPath = result.question_paper_path;
                this.showUploadStatus(
                    `Files processed successfully! 
                    Syllabus documents: ${result.syllabus_docs}, 
                    Textbook documents: ${result.textbook_docs}`, 
                    'success'
                );
                this.showValidationSection();
            } else {
                this.showError(result.error || 'Upload failed');
            }
        } catch (error) {
            this.showError('Network error during upload: ' + error.message);
        }
    }

    async startValidation() {
        if (!this.questionPaperPath) {
            this.showError('No question paper available for validation');
            return;
        }

        this.showValidationProgress(true);
        document.getElementById('validateBtn').disabled = true;

        try {
            const response = await fetch('/validate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    question_paper_path: this.questionPaperPath
                })
            });

            const result = await response.json();

            if (response.ok) {
                this.validationResults = result.results;
                this.displayResults();
                this.showValidationProgress(false);
            } else {
                let errorMessage = result.error || 'Validation failed';
                
                // Handle specific API errors
                if (response.status === 400 && errorMessage.includes('API key expired')) {
                    errorMessage = '🔑 API Key Expired: Please get a new Gemini API key from Google AI Studio and update the app.py file.';
                } else if (response.status === 429 && errorMessage.includes('quota exceeded')) {
                    errorMessage = '⚠️ API Quota Exceeded: You have reached the daily limit of 500 requests for the free tier. Please wait until tomorrow or upgrade your plan.';
                }
                
                this.showError(errorMessage);
                this.showValidationProgress(false);
            }
        } catch (error) {
            this.showError('Network error during validation: ' + error.message);
            this.showValidationProgress(false);
        } finally {
            document.getElementById('validateBtn').disabled = false;
        }
    }

    showUploadStatus(message, type) {
        const statusSection = document.getElementById('uploadStatus');
        const messageDiv = document.getElementById('uploadMessage');
        
        statusSection.style.display = 'block';
        messageDiv.innerHTML = '';

        const messageElement = document.createElement('div');
        messageElement.className = type;
        
        if (type === 'loading') {
            messageElement.innerHTML = `
                <div class="loading">
                    <div class="spinner"></div>
                    ${message}
                </div>
            `;
        } else {
            messageElement.textContent = message;
        }
        
        messageDiv.appendChild(messageElement);
    }

    showValidationSection() {
        document.getElementById('validationSection').style.display = 'block';
    }

    showValidationProgress(show) {
        const progressDiv = document.getElementById('validationProgress');
        const progressFill = document.getElementById('progressFill');
        const progressText = document.getElementById('progressText');
        
        if (show) {
            progressDiv.style.display = 'block';
            progressText.textContent = 'Processing questions...';
            
            // Simulate progress
            let progress = 0;
            const interval = setInterval(() => {
                progress += 2;
                progressFill.style.width = progress + '%';
                if (progress >= 90) {
                    clearInterval(interval);
                }
            }, 100);
        } else {
            progressDiv.style.display = 'none';
            progressFill.style.width = '0%';
        }
    }

    displayResults() {
        const resultsSection = document.getElementById('resultsSection');
        const resultsContainer = document.getElementById('resultsContainer');
        
        resultsSection.style.display = 'block';
        
        // Update summary statistics
        this.updateSummaryStats();
        
        // Clear previous results
        resultsContainer.innerHTML = '';
        
        // Display each question
        this.validationResults.forEach(result => {
            const questionCard = this.createQuestionCard(result);
            resultsContainer.appendChild(questionCard);
        });
    }

    updateSummaryStats() {
        const inSyllabusCount = this.validationResults.filter(r => r.syllabus_status === 'IN_SYLLABUS').length;
        const outSyllabusCount = this.validationResults.filter(r => r.syllabus_status === 'OUT_OF_SYLLABUS').length;
        const inTextbookCount = this.validationResults.filter(r => r.textbook_status === 'YES_IN_TEXTBOOK').length;
        
        document.getElementById('inSyllabusCount').textContent = inSyllabusCount;
        document.getElementById('outSyllabusCount').textContent = outSyllabusCount;
        document.getElementById('inTextbookCount').textContent = inTextbookCount;
    }

    createQuestionCard(result) {
        const card = document.createElement('div');
        card.className = 'question-card';
        card.setAttribute('data-syllabus-status', result.syllabus_status);
        
        const syllabusStatusClass = result.syllabus_status === 'IN_SYLLABUS' ? 'in-syllabus' : 'out-syllabus';
        
        let textbookBadge = '';
        if (result.textbook_status === 'YES_IN_TEXTBOOK') {
            textbookBadge = '<span class="status-badge in-textbook">In Textbook</span>';
        } else if (result.textbook_status === 'NO_IN_PROVIDED_TEXTBOOK_EXCERPTS') {
            textbookBadge = '<span class="status-badge not-in-textbook">Not in Textbook</span>';
        }
        
        card.innerHTML = `
            <div class="question-header">
                <div class="question-id">${result.question_id}</div>
                <div class="status-badges">
                    <span class="status-badge ${syllabusStatusClass}">
                        ${result.syllabus_status === 'IN_SYLLABUS' ? 'In Syllabus' : 'Out of Syllabus'}
                    </span>
                    ${textbookBadge}
                </div>
            </div>
            
            <div class="question-text">
                ${result.question_text}
            </div>
            
            <div class="reasoning-section">
                <div class="reasoning-title">Syllabus Analysis</div>
                <div class="reasoning-text">${result.syllabus_reasoning}</div>
            </div>
            
            ${result.textbook_reasoning ? `
                <div class="reasoning-section">
                    <div class="reasoning-title">Textbook Analysis</div>
                    <div class="reasoning-text">${result.textbook_reasoning}</div>
                </div>
            ` : ''}
        `;
        
        return card;
    }

    filterResults(filter) {
        const cards = document.querySelectorAll('.question-card');
        
        cards.forEach(card => {
            const syllabusStatus = card.getAttribute('data-syllabus-status');
            
            if (filter === 'all' || syllabusStatus === filter) {
                card.style.display = 'block';
            } else {
                card.style.display = 'none';
            }
        });
    }

    downloadResults() {
        const dataStr = JSON.stringify(this.validationResults, null, 2);
        const dataBlob = new Blob([dataStr], {type: 'application/json'});
        
        const link = document.createElement('a');
        link.href = URL.createObjectURL(dataBlob);
        link.download = `validation_results_${new Date().toISOString().slice(0, 10)}.json`;
        link.click();
    }

    showError(message) {
        const statusSection = document.getElementById('uploadStatus');
        const messageDiv = document.getElementById('uploadMessage');
        
        statusSection.style.display = 'block';
        messageDiv.innerHTML = `<div class="error">${message}</div>`;
    }
}

// Initialize the application
document.addEventListener('DOMContentLoaded', () => {
    new QPScrutiniser();
});
