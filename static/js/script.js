document.addEventListener('DOMContentLoaded', function() {
    // Elements
    const uploadArea = document.getElementById('upload-area');
    const fileInput = document.getElementById('file-input');
    const browseButton = document.getElementById('browse-button');
    const fileInfo = document.getElementById('file-info');
    const fileName = document.getElementById('file-name');
    const fileSize = document.getElementById('file-size');
    const removeFileBtn = document.getElementById('remove-file');
    const splitOptions = document.getElementById('split-options');
    const splitForm = document.getElementById('split-form');
    const resultsSection = document.getElementById('results-section');
    const segmentsList = document.getElementById('segments-list');
    const downloadAllBtn = document.getElementById('download-all');
    const progressContainer = document.getElementById('progress-container');
    const progressBar = document.getElementById('progress-bar');
    const errorToast = document.getElementById('error-toast');
    const errorMessage = document.getElementById('error-message');
    
    // Bootstrap toast initialization
    const toast = new bootstrap.Toast(errorToast);
    
    // State
    let currentFile = null;
    let sessionId = null;
    
    // Event listeners
    browseButton.addEventListener('click', () => fileInput.click());
    
    fileInput.addEventListener('change', handleFileSelection);
    
    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('active');
    });
    
    uploadArea.addEventListener('dragleave', () => {
        uploadArea.classList.remove('active');
    });
    
    // Add event listener for split type change
    const splitType = document.getElementById('split-type');
    const sizeUnit = document.getElementById('size-unit');
    
    splitType.addEventListener('change', (e) => {
        if (e.target.value === 'seconds') {
            sizeUnit.textContent = '(seconds)';
        } else if (e.target.value === 'megabytes') {
            sizeUnit.textContent = '(MB)';
        }
    });
    
    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('active');
        
        if (e.dataTransfer.files.length) {
            handleFile(e.dataTransfer.files[0]);
        }
    });
    
    removeFileBtn.addEventListener('click', resetUploadState);
    
    splitForm.addEventListener('submit', handleSplitRequest);
    
    downloadAllBtn.addEventListener('click', downloadAllSegments);
    
    window.addEventListener('beforeunload', cleanupFiles);
    
    // Functions
    function handleFileSelection(e) {
        if (e.target.files.length) {
            handleFile(e.target.files[0]);
        }
    }
    
    function handleFile(file) {
        // Check file type
        const allowedTypes = ['audio/mp3', 'audio/mpeg', 'audio/wav', 'audio/ogg', 'audio/m4a', 'audio/flac'];
        const fileType = file.type;
        
        if (!allowedTypes.includes(fileType) && 
            !file.name.match(/\.(mp3|wav|ogg|m4a|flac)$/i)) {
            showError("Invalid file type. Please upload an audio file (MP3, WAV, OGG, M4A, FLAC).");
            return;
        }
        
        // Check file size (max 50MB)
        if (file.size > 50 * 1024 * 1024) {
            showError("File is too large. Maximum size is 50MB.");
            return;
        }
        
        // Set current file
        currentFile = file;
        
        // Update UI
        showFileInfo(file);
        
        // Upload file
        uploadFile(file);
    }
    
    function showFileInfo(file) {
        fileName.textContent = file.name;
        fileSize.textContent = formatFileSize(file.size);
        fileInfo.classList.remove('d-none');
        uploadArea.classList.add('d-none');
    }
    
    function formatFileSize(bytes) {
        if (bytes < 1024) return bytes + ' bytes';
        else if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        else return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }
    
    function resetUploadState() {
        currentFile = null;
        fileInput.value = '';
        fileInfo.classList.add('d-none');
        uploadArea.classList.remove('d-none');
        splitOptions.classList.add('d-none');
        resultsSection.classList.add('d-none');
        progressContainer.classList.add('d-none');
        segmentsList.innerHTML = '';
    }
    
    function uploadFile(file) {
        // Show progress container
        progressContainer.classList.remove('d-none');
        progressBar.style.width = '0%';
        
        const formData = new FormData();
        formData.append('file', file);
        
        const xhr = new XMLHttpRequest();
        
        xhr.open('POST', '/upload', true);
        
        xhr.upload.onprogress = (e) => {
            if (e.lengthComputable) {
                const percent = (e.loaded / e.total) * 100;
                progressBar.style.width = percent + '%';
            }
        };
        
        xhr.onload = function() {
            if (xhr.status === 200) {
                const response = JSON.parse(xhr.responseText);
                if (response.success) {
                    progressBar.style.width = '100%';
                    sessionId = response.session_id;
                    
                    // Show split options
                    setTimeout(() => {
                        splitOptions.classList.remove('d-none');
                        progressContainer.classList.add('d-none');
                    }, 500);
                } else {
                    showError(response.error || "Error uploading file");
                    resetUploadState();
                }
            } else {
                try {
                    const response = JSON.parse(xhr.responseText);
                    showError(response.error || "Error uploading file");
                } catch (e) {
                    showError("Error uploading file");
                }
                resetUploadState();
            }
        };
        
        xhr.onerror = function() {
            showError("Network error occurred while uploading");
            resetUploadState();
        };
        
        xhr.send(formData);
    }
    
    function handleSplitRequest(e) {
        e.preventDefault();
        
        const segmentSize = document.getElementById('segment-size').value;
        const splitType = document.getElementById('split-type').value;
        
        if (!segmentSize || segmentSize <= 0) {
            showError("Please enter a valid segment size");
            return;
        }
        
        // Show progress with message
        progressContainer.classList.remove('d-none');
        progressBar.style.width = '0%';
        
        // Show processing notification
        const processingMsg = document.createElement('div');
        processingMsg.className = 'alert alert-info mt-2';
        processingMsg.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i> Processing your audio file. This may take several minutes for large files...';
        progressContainer.after(processingMsg);
        
        // Simulate progress for better UX during long operations
        let progress = 0;
        const progressInterval = setInterval(() => {
            if (progress < 95) { // Max to 95% - real completion will set it to 100%
                progress += (progress < 50) ? 0.5 : 0.1; // Slow down as it gets higher
                progressBar.style.width = progress + '%';
            }
        }, 300);
        
        // Increase timeout for large files
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 300000); // 5 minute timeout
        
        // Send split request
        const formData = new FormData();
        formData.append('segment_size', segmentSize);
        formData.append('split_type', splitType);
        
        fetch('/split', {
            method: 'POST',
            body: formData,
            signal: controller.signal
        })
        .then(response => {
            clearTimeout(timeoutId);
            clearInterval(progressInterval);
            progressBar.style.width = '100%';
            
            return response.json();
        })
        .then(data => {
            if (data.success) {
                displayResults(data);
            } else {
                throw new Error(data.error || "Error splitting file");
            }
        })
        .catch(error => {
            // Handle timeout errors specifically
            if (error.name === 'AbortError') {
                showError("Operation timed out. The file may be too large to process.");
            } else {
                showError(error.message || "Error splitting file");
            }
        })
        .finally(() => {
            clearInterval(progressInterval);
            progressContainer.classList.add('d-none');
            processingMsg.remove();
        });
    }
    
    function displayResults(data) {
        // Clear previous results
        segmentsList.innerHTML = '';
        
        // Add summary information
        const summaryDiv = document.createElement('div');
        summaryDiv.className = 'alert alert-success mb-3';
        summaryDiv.innerHTML = `
            <h6><i class="fas fa-check-circle me-2"></i>Split Complete!</h6>
            <p class="mb-1">Created ${data.segment_count} segments</p>
            <p class="mb-0">Total output size: ${data.total_size_mb}MB</p>
        `;
        segmentsList.appendChild(summaryDiv);
        
        // Add each file to the list
        data.files.forEach((file, index) => {
            const listItem = document.createElement('a');
            listItem.href = `/download/${encodeURIComponent(file)}`;
            listItem.className = 'list-group-item list-group-item-action d-flex justify-content-between align-items-center';
            
            const fileInfo = document.createElement('div');
            fileInfo.innerHTML = `
                <i class="fas fa-music me-2"></i>
                <span>${file}</span>
                <span class="badge bg-info rounded-pill ms-2">Segment ${index + 1}</span>
            `;
            
            const downloadBtn = document.createElement('button');
            downloadBtn.className = 'btn btn-sm btn-outline-info';
            downloadBtn.innerHTML = '<i class="fas fa-download"></i>';
            
            listItem.appendChild(fileInfo);
            listItem.appendChild(downloadBtn);
            
            listItem.addEventListener('click', (e) => {
                e.preventDefault();
                window.location.href = listItem.href;
            });
            
            segmentsList.appendChild(listItem);
        });
        
        // Show results section
        resultsSection.classList.remove('d-none');
    }
    
    function downloadAllSegments() {
        window.location.href = '/download-all';
    }
    
    function showError(message) {
        errorMessage.textContent = message;
        toast.show();
    }
    
    function cleanupFiles() {
        // Send cleanup request when user leaves the page
        if (sessionId) {
            navigator.sendBeacon('/cleanup', JSON.stringify({ session_id: sessionId }));
        }
    }
});
