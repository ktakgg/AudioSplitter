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
    const uploadProgressContainer = document.getElementById('upload-progress-container');
    const uploadProgressBar = document.getElementById('upload-progress-bar');
    const errorToast = document.getElementById('error-toast');
    const errorMessage = document.getElementById('error-message');
    
    // Bootstrap toast initialization
    const toast = new bootstrap.Toast(errorToast);
    
    // State
    let currentFile = null;
    let sessionId = null;
    let maxFileSize = 200 * 1024 * 1024; // Default 200MB
    let maxFileSizeMB = 200;
    
    // Fetch server configuration on load
    fetch('/config')
        .then(response => response.json())
        .then(config => {
            maxFileSize = config.max_file_size;
            maxFileSizeMB = config.max_file_size_mb;
        })
        .catch(error => {
            console.warn('Failed to load server config, using defaults:', error);
        });
    
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
            sizeUnit.textContent = '（秒）';
        } else if (e.target.value === 'megabytes') {
            sizeUnit.textContent = '（MB）';
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
    
    // Add event listener for manual delete button
    const deleteFilesBtn = document.getElementById('delete-files-btn');
    if (deleteFilesBtn) {
        deleteFilesBtn.addEventListener('click', () => {
            showDeleteConfirmation();
        });
    }
    
    // Add event listener for manual cleanup button
    const manualCleanupBtn = document.getElementById('manual-cleanup-btn');
    if (manualCleanupBtn) {
        manualCleanupBtn.addEventListener('click', () => {
            const confirmed = confirm('セッションをクリーンアップしますか？\n\nこの操作により、アップロードした音声ファイルと分割ファイルがすべて削除されます。');
            if (confirmed) {
                cleanupFiles();
            }
        });
    }
    
    // Disable automatic cleanup to prevent interference with downloads
    // window.addEventListener('beforeunload', cleanupFiles);
    
    // Functions
    function handleFileSelection(e) {
        if (e.target.files.length) {
            handleFile(e.target.files[0]);
        }
    }
    
    function handleFile(file) {
        // Enhanced file type checking
        const allowedTypes = ['audio/mp3', 'audio/mpeg', 'audio/wav', 'audio/wave', 'audio/x-wav', 'audio/ogg', 'audio/m4a', 'audio/mp4', 'audio/x-m4a', 'audio/flac', 'audio/x-flac', 'audio/aac', 'audio/wma'];
        const allowedExtensions = /\.(mp3|wav|ogg|m4a|flac|aac|wma)$/i;
        
        console.log('File type:', file.type);
        console.log('File name:', file.name);
        
        // Check file extension (more reliable than MIME type)
        if (!allowedExtensions.test(file.name)) {
            showError("無効なファイル形式です。音声ファイル（MP3, WAV, OGG, M4A, FLAC, AAC, WMA）をアップロードしてください。");
            return;
        }
        
        // Check file size using server-configured limit
        if (file.size > maxFileSize) {
            showError(`ファイルサイズが大きすぎます（${formatFileSize(file.size)}）。最大サイズは${maxFileSizeMB}MBです。より小さなファイルを選択してください。`);
            return;
        }
        
        // Check if file is empty
        if (file.size === 0) {
            showError("ファイルが空です。有効な音声ファイルを選択してください。");
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
        // Show upload progress container
        uploadProgressContainer.classList.remove('d-none');
        uploadProgressBar.style.width = '0%';
        
        const formData = new FormData();
        formData.append('file', file);
        
        const xhr = new XMLHttpRequest();
        
        // Set timeout to 5 minutes for large files
        xhr.timeout = 300000;
        
        xhr.open('POST', '/upload', true);
        
        xhr.upload.onprogress = (e) => {
            if (e.lengthComputable) {
                const percent = (e.loaded / e.total) * 100;
                uploadProgressBar.style.width = percent + '%';
            }
        };
        
        xhr.onload = function() {
            uploadProgressContainer.classList.add('d-none');
            
            if (xhr.status === 200) {
                try {
                    const response = JSON.parse(xhr.responseText);
                    if (response.success) {
                        uploadProgressBar.style.width = '100%';
                        sessionId = response.session_id;
                        
                        console.log('Upload successful:', response);
                        
                        // Show split options
                        setTimeout(() => {
                            splitOptions.classList.remove('d-none');
                        }, 300);
                    } else {
                        showError(response.error || "Upload failed - please try again");
                        resetUploadState();
                    }
                } catch (e) {
                    console.error('Error parsing response:', e);
                    showError("Invalid response from server");
                    resetUploadState();
                }
            } else if (xhr.status === 413) {
                try {
                    const response = JSON.parse(xhr.responseText);
                    showError(response.error || `ファイルサイズが大きすぎます。最大サイズは${maxFileSizeMB}MBです。より小さなファイルを選択してください。`);
                } catch (e) {
                    showError(`ファイルサイズが大きすぎます。最大サイズは${maxFileSizeMB}MBです。より小さなファイルを分割してからアップロードしてください。`);
                }
                resetUploadState();
            } else {
                try {
                    const response = JSON.parse(xhr.responseText);
                    showError(response.error || `Upload failed (${xhr.status})`);
                } catch (e) {
                    showError(`Upload failed - server returned status ${xhr.status}`);
                }
                resetUploadState();
            }
        };
        
        xhr.onerror = function() {
            uploadProgressContainer.classList.add('d-none');
            showError("Network error occurred while uploading. Please check your connection and try again.");
            resetUploadState();
        };
        
        xhr.ontimeout = function() {
            uploadProgressContainer.classList.add('d-none');
            showError("Upload timed out. Please try with a smaller file or check your connection.");
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
                showError("処理がタイムアウトしました。ファイルサイズが大きすぎる可能性があります。");
            } else {
                showError(error.message || "ファイル分割中にエラーが発生しました");
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
            <h6><i class="fas fa-check-circle me-2"></i>分割完了！</h6>
            <p class="mb-1">${data.segment_count}個のセグメントを作成しました</p>
            <p class="mb-0">合計出力サイズ: ${data.total_size_mb}MB</p>
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
            downloadBtn.className = 'btn btn-sm btn-outline-info download-btn';
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
        // Show downloading status and disable buttons
        const downloadAllBtn = document.getElementById('download-all');
        const deleteFilesBtn = document.getElementById('delete-files-btn');
        const manualCleanupBtn = document.getElementById('manual-cleanup-btn');
        
        // Disable all buttons during download
        downloadAllBtn.disabled = true;
        downloadAllBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>ダウンロード中...';
        
        if (deleteFilesBtn) deleteFilesBtn.disabled = true;
        if (manualCleanupBtn) manualCleanupBtn.disabled = true;
        
        // Use fetch to monitor download progress
        fetch('/download-all')
            .then(response => {
                if (!response.ok) {
                    throw new Error('ダウンロードに失敗しました');
                }
                
                const contentLength = response.headers.get('content-length');
                const total = parseInt(contentLength, 10);
                let loaded = 0;
                
                const reader = response.body.getReader();
                const chunks = [];
                
                function pump() {
                    return reader.read().then(({ done, value }) => {
                        if (done) {
                            // Download completed
                            const blob = new Blob(chunks);
                            const url = window.URL.createObjectURL(blob);
                            const a = document.createElement('a');
                            a.href = url;
                            a.download = 'audio_segments.zip';
                            a.style.display = 'none';
                            document.body.appendChild(a);
                            a.click();
                            document.body.removeChild(a);
                            window.URL.revokeObjectURL(url);
                            
                            // Re-enable buttons after download completes
                            downloadAllBtn.disabled = false;
                            downloadAllBtn.innerHTML = '<i class="fas fa-check me-2"></i>ダウンロード完了';
                            
                            if (deleteFilesBtn) deleteFilesBtn.disabled = false;
                            if (manualCleanupBtn) manualCleanupBtn.disabled = false;
                            
                            // Wait a moment for the browser to process the download
                            setTimeout(() => {
                                // Show deletion confirmation popup after download completion
                                showDeleteConfirmation('download');
                            }, 1500);
                            
                            return;
                        }
                        
                        chunks.push(value);
                        loaded += value.length;
                        
                        if (total) {
                            const progress = Math.round((loaded / total) * 100);
                            downloadAllBtn.innerHTML = `<i class="fas fa-spinner fa-spin me-2"></i>ダウンロード中... ${progress}%`;
                        }
                        
                        return pump();
                    });
                }
                
                return pump();
            })
            .catch(error => {
                console.error('Download error:', error);
                
                // Re-enable buttons on error
                downloadAllBtn.disabled = false;
                downloadAllBtn.innerHTML = '<i class="fas fa-download me-2"></i>すべてのセグメントをZIPでダウンロード';
                
                if (deleteFilesBtn) deleteFilesBtn.disabled = false;
                if (manualCleanupBtn) manualCleanupBtn.disabled = false;
                
                showError('ダウンロードに失敗しました: ' + error.message);
            });
    }
    
    function showDeleteConfirmation() {
        // Check if this is called from download button or manual delete button
        const isFromDownload = arguments[0] === 'download';
        
        let message;
        if (isFromDownload) {
            message = 'ダウンロードが完了しました。\n\nサーバー上の分割ファイルを削除しますか？\n（セキュリティのため削除を推奨します）';
        } else {
            message = 'サーバー上の分割ファイルを削除しますか？\n\n削除後はファイルをダウンロードできなくなります。\n（セキュリティのため削除を推奨します）';
        }
        
        const confirmed = confirm(message);
        
        if (confirmed) {
            deleteServerFiles();
        }
    }
    
    function deleteServerFiles() {
        if (!sessionId) {
            showError('セッション情報が見つかりません');
            return;
        }
        
        fetch('/delete-files', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ session_id: sessionId })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Show success message
                const successDiv = document.createElement('div');
                successDiv.className = 'alert alert-info mb-3';
                successDiv.innerHTML = `
                    <h6><i class="fas fa-info-circle me-2"></i>ファイル削除完了</h6>
                    <p class="mb-0">サーバー上の分割ファイルを削除しました。</p>
                `;
                
                // Insert at the top of results
                const segmentsList = document.getElementById('segments-list');
                segmentsList.insertBefore(successDiv, segmentsList.firstChild);
                
                // Disable download buttons
                document.querySelectorAll('.download-btn').forEach(btn => {
                    btn.disabled = true;
                    btn.innerHTML = '<i class="fas fa-ban"></i>';
                    btn.classList.remove('btn-outline-info');
                    btn.classList.add('btn-secondary');
                });
                
                // Disable individual download links
                document.querySelectorAll('.list-group-item').forEach(item => {
                    item.style.pointerEvents = 'none';
                    item.style.opacity = '0.5';
                    item.classList.remove('list-group-item-action');
                });
                
                // Disable upload section
                const fileInfoSection = document.getElementById('file-info');
                const splitOptions = document.getElementById('split-options');
                const removeFileBtn = document.getElementById('remove-file');
                const splitButton = document.getElementById('split-button');
                
                if (fileInfoSection) {
                    fileInfoSection.style.opacity = '0.5';
                    fileInfoSection.style.pointerEvents = 'none';
                }
                
                if (splitOptions) {
                    splitOptions.style.opacity = '0.5';
                    splitOptions.style.pointerEvents = 'none';
                }
                
                if (removeFileBtn) {
                    removeFileBtn.disabled = true;
                    removeFileBtn.innerHTML = '<i class="fas fa-ban"></i> 削除済み';
                    removeFileBtn.classList.remove('btn-outline-danger');
                    removeFileBtn.classList.add('btn-secondary');
                }
                
                if (splitButton) {
                    splitButton.disabled = true;
                    splitButton.innerHTML = '<i class="fas fa-ban me-2"></i>ファイル削除済み';
                    splitButton.classList.remove('btn-success');
                    splitButton.classList.add('btn-secondary');
                }
                
                const downloadAllBtn = document.getElementById('download-all');
                if (downloadAllBtn) {
                    downloadAllBtn.disabled = true;
                    downloadAllBtn.innerHTML = '<i class="fas fa-check me-2"></i>削除済み';
                    downloadAllBtn.classList.remove('btn-outline-primary');
                    downloadAllBtn.classList.add('btn-secondary');
                }
                
                const deleteFilesBtn = document.getElementById('delete-files-btn');
                if (deleteFilesBtn) {
                    deleteFilesBtn.disabled = true;
                    deleteFilesBtn.innerHTML = '<i class="fas fa-check me-2"></i>削除済み';
                    deleteFilesBtn.classList.remove('btn-outline-danger');
                    deleteFilesBtn.classList.add('btn-secondary');
                }
                
                const manualCleanupBtn = document.getElementById('manual-cleanup-btn');
                if (manualCleanupBtn) {
                    manualCleanupBtn.disabled = true;
                    manualCleanupBtn.innerHTML = '<i class="fas fa-check me-2"></i>削除済み';
                    manualCleanupBtn.classList.remove('btn-outline-secondary');
                    manualCleanupBtn.classList.add('btn-secondary');
                }
            } else {
                showError(data.error || 'ファイル削除中にエラーが発生しました');
            }
        })
        .catch(error => {
            showError('ファイル削除中にエラーが発生しました: ' + error.message);
        });
    }
    
    function showError(message) {
        errorMessage.textContent = message;
        toast.show();
    }
    
    function cleanupFiles() {
        // Manual cleanup function - only called explicitly
        if (!sessionId) {
            showError('セッション情報が見つかりません');
            return;
        }
        
        fetch('/cleanup', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ session_id: sessionId })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                console.log('ファイルクリーンアップ完了');
            }
        })
        .catch(error => {
            console.error('クリーンアップエラー:', error);
        });
    }
});
