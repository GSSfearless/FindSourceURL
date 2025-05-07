const express = require('express');
const multer = require('multer');
const path = require('path');
const fs = require('fs'); // File System module
const { findImageSourceUrls } = require('./scraper'); // Import our scraper function

const app = express();
const port = process.env.PORT || 3000; // Use Vercel's port or 3000 for local

// --- Multer Configuration for file uploads ---
// Create an 'uploads' directory if it doesn't exist
const uploadsDir = path.join(__dirname, 'uploads');
if (!fs.existsSync(uploadsDir)) {
    fs.mkdirSync(uploadsDir);
}

const storage = multer.diskStorage({
    destination: function (req, file, cb) {
        cb(null, uploadsDir); // Save uploaded files to the 'uploads' directory
    },
    filename: function (req, file, cb) {
        // Create a unique filename to avoid overwriting
        cb(null, file.fieldname + '-' + Date.now() + path.extname(file.originalname));
    }
});

const upload = multer({ 
    storage: storage,
    limits: { fileSize: 10 * 1024 * 1024 }, // Limit file size to 10MB
    fileFilter: function (req, file, cb) {
        // Accept only image files
        const filetypes = /jpeg|jpg|png|gif|bmp|webp|heic|heif/;
        const mimetype = filetypes.test(file.mimetype);
        const extname = filetypes.test(path.extname(file.originalname).toLowerCase());
        if (mimetype && extname) {
            return cb(null, true);
        }
        cb(new Error('Error: File upload only supports the following filetypes - ' + filetypes));
    }
});

// --- Middleware ---
app.use(express.json()); // To parse JSON bodies
app.use(express.urlencoded({ extended: true })); // To parse URL-encoded bodies

// Serve a simple frontend (we'll create index.html later)
// For Vercel, it often serves from the 'public' directory or root.
// For now, let's assume we might put an index.html in the root of this backend, or serve it differently later.
app.get('/', (req, res) => {
    // res.send('<h1>FindSourceURL Backend is Running!</h1><p>Upload to /api/find-source</p>');
    // We will serve index.html from a more appropriate location soon.
    res.sendFile(path.join(__dirname, '..', 'index.html')); // Tentatively serve from one level up for now
});

// --- API Endpoint ---
app.post('/api/find-source', upload.single('imageFile'), async (req, res) => {
    console.log('[Server] Received request to /api/find-source');
    if (!req.file) {
        return res.status(400).json({ error: 'No image file uploaded.' });
    }

    const imagePath = req.file.path;
    console.log(`[Server] Image uploaded to: ${imagePath}`);

    try {
        // IMPORTANT: Puppeteer might run headless on the server by default.
        // For local testing, you might have set headless: false in scraper.js.
        // On Vercel, puppeteer will need to run headless.
        // The findImageSourceUrls function in scraper.js currently defaults to headless:false.
        // We need to ensure scraper.js can run headless on the server.
        const urls = await findImageSourceUrls(imagePath);
        
        // Clean up the uploaded file after processing
        fs.unlink(imagePath, (err) => {
            if (err) {
                console.error('[Server] Error deleting uploaded file:', err);
            }
        });

        if (urls && urls.length > 0) {
            res.json({ sourceUrls: urls });
        } else {
            res.json({ sourceUrls: [], message: 'No source URLs found or an error occurred during scraping.' });
        }
    } catch (error) {
        console.error('[Server] Error processing image:', error);
        // Clean up uploaded file in case of error too
        fs.unlink(imagePath, (err) => {
            if (err) {
                console.error('[Server] Error deleting uploaded file after error:', err);
            }
        });
        res.status(500).json({ error: 'Failed to find image source. ' + error.message });
    }
});

// --- Start Server ---
app.listen(port, () => {
    console.log(`[Server] FindSourceURL backend listening on port ${port}`);
});

// Export the app for Vercel (Vercel looks for a default export or an app object)
module.exports = app; 