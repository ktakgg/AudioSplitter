// Debug script to understand deployment environment differences
console.log('=== Deployment Environment Debug ===');
console.log('User Agent:', navigator.userAgent);
console.log('Location:', window.location.href);

// Check if config endpoint is accessible
fetch('/config')
    .then(response => {
        console.log('Config response status:', response.status);
        return response.json();
    })
    .then(config => {
        console.log('Server config:', config);
        console.log('Max file size bytes:', config.max_file_size);
        console.log('Max file size MB:', config.max_file_size_mb);
        
        // Test file size calculation
        const testSize = 39003507; // Your file size
        console.log('Test file size:', testSize);
        console.log('Is file too large?', testSize > config.max_file_size);
        console.log('Difference:', config.max_file_size - testSize);
    })
    .catch(error => {
        console.error('Config fetch failed:', error);
    });

// Check window variables
console.log('window.MAX_FILE_SIZE:', window.MAX_FILE_SIZE);
console.log('window.MAX_FILE_SIZE_MB:', window.MAX_FILE_SIZE_MB);