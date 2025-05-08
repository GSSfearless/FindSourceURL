const express = require('express');
const multer = require('multer');
const path = require('path');
const { spawn } = require('child_process'); // For running the scraper script
const fs = require('fs'); // For deleting the file

const app = express();
const port = process.env.PORT || 3000;

// --- Middleware ---
// Serve static files from a 'public' directory (for later frontend)
app.use(express.static(path.join(__dirname, 'public')));
// For parsing application/json
app.use(express.json());
// For parsing application/x-www-form-urlencoded
app.use(express.urlencoded({ extended: true }));

// --- File Upload Setup (using multer) ---
// Configure multer for file storage
const storage = multer.diskStorage({
    destination: function (req, file, cb) {
        cb(null, 'uploads/'); // Ensure 'uploads/' directory exists
    },
    filename: function (req, file, cb) {
        // cb(null, file.fieldname + '-' + Date.now() + path.extname(file.originalname));
        cb(null, Date.now() + '-' + file.originalname); // Simpler filename
    }
});

const upload = multer({
    storage: storage,
    limits: { fileSize: 10 * 1024 * 1024 }, // 10MB file size limit
    fileFilter: function (req, file, cb) {
        checkFileType(file, cb);
    }
});

// Helper function to check file type
function checkFileType(file, cb) {
    // Allowed ext
    const filetypes = /jpeg|jpg|png|gif/;
    // Check ext
    const extname = filetypes.test(path.extname(file.originalname).toLowerCase());
    // Check mime
    const mimetype = filetypes.test(file.mimetype);

    if (mimetype && extname) {
        return cb(null, true);
    } else {
        cb('Error: Images Only! (jpeg, jpg, png, gif)');
    }
}

// --- API Routes ---
app.post('/api/find-url', upload.single('screenshot'), (req, res) => {
    if (!req.file) {
        return res.status(400).json({ error: 'No file uploaded.' });
    }

    const imagePath = req.file.path;
    const absoluteImagePath = path.resolve(imagePath);
    console.log(`[API] Received file: ${imagePath}, absolute path: ${absoluteImagePath}`);

    const scraperProcess = spawn('node', [path.join(__dirname, 'scraper.js'), absoluteImagePath]);

    let stdoutData = '';
    let stderrData = '';

    scraperProcess.stdout.on('data', (data) => {
        stdoutData += data.toString();
        console.log(`[Scraper STDOUT]: ${data.toString().trim()}`);
    });

    scraperProcess.stderr.on('data', (data) => {
        stderrData += data.toString();
        console.error(`[Scraper STDERR]: ${data.toString().trim()}`);
    });

    scraperProcess.on('error', (error) => {
        console.error(`[API] Failed to start scraper process: ${error.message}`);
        // Clean up uploaded file
        fs.unlink(imagePath, (unlinkErr) => {
            if (unlinkErr) console.error(`[API] Error deleting file ${imagePath}: ${unlinkErr.message}`);
        });
        return res.status(500).json({ error: 'Failed to start scraping process.', details: error.message });
    });

    scraperProcess.on('close', (code) => {
        console.log(`[API] Scraper process exited with code ${code}`);

        // Clean up uploaded file
        fs.unlink(imagePath, (unlinkErr) => {
            if (unlinkErr) console.error(`[API] Error deleting file ${imagePath} after script execution: ${unlinkErr.message}`);
            else console.log(`[API] Successfully deleted uploaded file: ${imagePath}`);
        });

        if (code !== 0) {
            return res.status(500).json({
                error: 'Scraping process failed.',
                details: stderrData || 'Scraper exited with a non-zero code but no stderr output.'
            });
        }

        // Parse stdoutData to extract URLs
        const lines = stdoutData.split('\n');
        const urls = [];
        let foundMarker = false;

        for (const line of lines) {
            if (line.includes('--- Found Source URLs ---')) {
                foundMarker = true;
                continue;
            }
            if (line.includes('--- No source URLs found for this image. ---')) {
                foundMarker = false; // Reset if this specific message is found (even after foundMarker was true)
                urls.length = 0; // Clear any URLs found before this message
                break;
            }
            if (foundMarker && line.trim() !== '') {
                urls.push(line.trim());
            }
        }

        if (urls.length > 0) {
            res.json({ urls: urls });
        } else if (stdoutData.includes('--- No source URLs found for this image. ---')) {
            res.json({ urls: [], message: 'No source URLs found for this image.' });
        } else if (stderrData.trim() !== '') { // If scraper exited with 0 but produced stderr
             res.status(500).json({
                error: 'Scraping process completed with code 0 but produced errors.',
                details: stderrData
            });
        } else {
            res.json({ urls: [], message: 'No source URLs found or output was not recognized.' });
        }
    });
});

// --- Error Handling Middleware ---
app.use((err, req, res, next) => {
    console.error("[API Error]", err.stack);
    if (err instanceof multer.MulterError) {
        return res.status(400).json({ error: `Multer error: ${err.message}` });
    } else if (err) {
        return res.status(500).json({ error: err.message || 'Something went wrong!' });
    }
    next();
});


// --- Start Server ---
app.listen(port, () => {
    console.log(`[API] Server listening on port ${port}`);
    // Create 'uploads' directory if it doesn't exist
    const uploadsDir = path.join(__dirname, 'uploads');
    if (!fs.existsSync(uploadsDir)) {
        fs.mkdirSync(uploadsDir);
        console.log(`[API] Created 'uploads' directory: ${uploadsDir}`);
    }
}); 