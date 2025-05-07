const puppeteer = require('puppeteer');
const https = require('https'); // Use built-in https module
const querystring = require('querystring'); // For building query strings

// Initialize 2Captcha Solver outside the function if API key is static
// Ensure TWOCAPTCHA_API_KEY is set as an environment variable
const captchApiKey = process.env.TWOCAPTCHA_API_KEY;
// Remove Solver initialization
// let captchaSolver;
// if (captchApiKey) {
//     captchaSolver = new Solver(captchApiKey);
//     console.log('[Scraper] 2Captcha Solver initialized.');
// } else {
//     console.warn('[Scraper] WARNING: TWOCAPTCHA_API_KEY environment variable not set. CAPTCHA solving will be skipped.');
// }

// Helper function for making HTTPS requests and returning JSON
function httpsRequest(options, postData = null) {
    return new Promise((resolve, reject) => {
        const req = https.request(options, (res) => {
            let data = '';
            res.on('data', (chunk) => {
                data += chunk;
            });
            res.on('end', () => {
                try {
                    // Check if response is likely plain text error before JSON parsing
                    if (res.statusCode >= 200 && res.statusCode < 300 && !data.startsWith('{')) {
                        // Handle potential plain text responses like CAPCHA_NOT_READY
                        resolve(data);
                    } else if (res.statusCode >= 200 && res.statusCode < 300) {
                         resolve(JSON.parse(data));
                    } else {
                        reject(new Error(`HTTP status code ${res.statusCode}: ${data}`));
                    }
                } catch (e) {
                    reject(new Error(`Failed to parse response JSON: ${e.message}. Response: ${data}`));
                }
            });
        });

        req.on('error', (e) => {
            reject(new Error(`HTTPS request failed: ${e.message}`));
        });

        if (postData) {
            req.write(postData);
        }

        req.end();
    });
}

/**
 * Attempts to solve reCAPTCHA using the 2Captcha HTTP API directly.
 * @param {Page} page Puppeteer page instance.
 * @returns {Promise<string|null>} Resolves with the CAPTCHA token or null if failed.
 */
async function handleCaptchaWith2CaptchaDirectAPI(page) {
    console.log('[Scraper] Attempting to solve CAPTCHA with 2Captcha Direct API...');

    if (!captchApiKey) {
        console.error('[Scraper] 2Captcha API key not set. Skipping CAPTCHA attempt.');
        return null;
    }

    try {
        const pageUrl = page.url();
        let sitekey = await page.evaluate(() => {
            const iframe = document.querySelector('iframe[src*="google.com/recaptcha"]');
            if (iframe) {
                const params = new URLSearchParams(new URL(iframe.src).search);
                return params.get('k');
            }
            const elWithSitekey = document.querySelector('[data-sitekey]');
            if (elWithSitekey) return elWithSitekey.getAttribute('data-sitekey');
            return null;
        });

        let dataS = await page.evaluate(() => {
            const elWithDataS = document.querySelector('[data-s]');
            return elWithDataS ? elWithDataS.getAttribute('data-s') : null;
        });

        if (!sitekey) {
            console.error('[Scraper] CRITICAL: Could not automatically find reCAPTCHA sitekey. Cannot proceed with 2Captcha.');
            return null;
        }

        console.log(`[Scraper] Found sitekey: ${sitekey}`);
        if (dataS) {
             console.log(`[Scraper] Found data-s: ${dataS}`);
        } else {
             console.warn('[Scraper] data-s not found. Proceeding without it, but might be required.');
        }

        // Step 1: Submit task to /in.php
        const inParams = {
            key: captchApiKey,
            method: 'userrecaptcha',
            googlekey: sitekey,
            pageurl: pageUrl,
            json: 1
        };
        if (dataS) {
            inParams['data-s'] = dataS; // Add data-s parameter directly
        }

        const postData = querystring.stringify(inParams);
        const inOptions = {
            hostname: '2captcha.com',
            port: 443,
            path: '/in.php',
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Content-Length': Buffer.byteLength(postData)
            }
        };

        console.log('[Scraper] Submitting task to 2Captcha /in.php...');
        const inResponse = await httpsRequest(inOptions, postData);

        if (!inResponse || inResponse.status !== 1) {
            throw new Error(`2Captcha /in.php error: ${inResponse.request || JSON.stringify(inResponse)}`);
        }

        const taskId = inResponse.request;
        console.log(`[Scraper] 2Captcha Task ID: ${taskId}. Polling for result...`);

        // Step 2: Poll /res.php for the result
        const resParams = {
            key: captchApiKey,
            action: 'get',
            id: taskId,
            json: 1
        };
        const resQueryString = querystring.stringify(resParams);
        const resOptions = {
            hostname: '2captcha.com',
            port: 443,
            path: `/res.php?${resQueryString}`,
            method: 'GET'
        };

        const startTime = Date.now();
        const timeoutMs = 180000; // 3 minutes timeout for polling
        const pollIntervalMs = 10000; // Poll every 10 seconds

        while (Date.now() - startTime < timeoutMs) {
            await new Promise(resolve => setTimeout(resolve, pollIntervalMs));
            console.log(`[Scraper] Polling 2Captcha /res.php for task ${taskId}...`);
            const resResponse = await httpsRequest(resOptions);

            // Check for "Not Ready" status (both plain text and JSON format)
            let isNotReady = false;
            if (typeof resResponse === 'string' && resResponse === 'CAPCHA_NOT_READY') {
                isNotReady = true;
            }
            if (typeof resResponse === 'object' && resResponse !== null && resResponse.status === 0 && resResponse.request === 'CAPCHA_NOT_READY') {
                 isNotReady = true;
            }

            if (isNotReady) {
                console.log('[Scraper] CAPCHA_NOT_READY, polling again...');
                continue;
            }

            // Check for success
            if (typeof resResponse === 'object' && resResponse !== null && resResponse.status === 1) {
                console.log('[Scraper] 2Captcha task solved!');
                return resResponse.request; // Return the token
            }

            // If it's not "Not Ready" and not Success, it's an error or unexpected response
            console.error('[Scraper] Received error or unexpected response from /res.php:', resResponse);
            throw new Error(`2Captcha /res.php error or unexpected response: ${typeof resResponse === 'string' ? resResponse : JSON.stringify(resResponse)}`);
        }

        // Timeout reached
        throw new Error(`2Captcha polling timed out after ${timeoutMs / 1000} seconds.`);

    } catch (error) {
        console.error('[Scraper] Error during 2Captcha Direct API process:', error.message || error);
        if(page) await page.screenshot({ path: 'error_screenshot_captcha_direct_api_failed.png' });
        return null; // Indicate failure
    }
}

/**
 * Scrapes Google Images reverse image search for source URLs.
 * @param {string} imagePath - Absolute path to the image file.
 * @returns {Promise<string[]>} - A promise that resolves to an array of found source URLs.
 */
async function findImageSourceUrls(imagePath) {
    console.log(`[Scraper] Starting browser for image: ${imagePath}`);
    let browser = null;
    let page = null; // Declare page here to access in final catch
    const foundUrls = [];

    try {
        browser = await puppeteer.launch({ headless: false });
        page = await browser.newPage(); // Assign to outer scope variable
        await page.setViewport({ width: 1366, height: 768 });
        
        console.log('[Scraper] Navigating to Google Images...');
        await page.goto('https://images.google.com/', { waitUntil: 'networkidle2' });

        console.log('[Scraper] Looking for camera icon...');
        const cameraIconSelector = 'div[aria-label="按图搜索"]';
        try {
            await page.waitForSelector(cameraIconSelector, { visible: true, timeout: 10000 });
            await page.click(cameraIconSelector);
        } catch (error) {
            console.error(`[Scraper] Error finding or clicking camera icon (${cameraIconSelector}):`, error);
            throw new Error('Could not interact with camera icon.');
        }

        console.log('[Scraper] Waiting for upload panel content (上传文件 link)...');
        const uploadLinkSelector = 'span[jsname="tAPGc"]';
        try {
            await page.waitForSelector(uploadLinkSelector, { visible: true, timeout: 20000 });
            console.log('[Scraper] Upload panel link found. Adding a short delay for stability...');
            await new Promise(resolve => setTimeout(resolve, 1000));
            console.log('[Scraper] Upload panel content should be ready.');
        } catch (error) {
            console.error(`[Scraper] Error waiting for upload panel content (${uploadLinkSelector}):`, error);
            if (page) await page.screenshot({ path: 'error_screenshot_upload_panel.png' });
            throw new Error('Upload panel did not appear or was not ready.');
        }

        console.log('[Scraper] Looking for file input element...');
        const fileInputSelector = 'input[type="file"]';
        try {
            const inputUploadHandle = await page.waitForSelector(fileInputSelector, { timeout: 5000 });
            await inputUploadHandle.uploadFile(imagePath);
            console.log('[Scraper] File selected for upload.');
        } catch (error) {
             console.error(`[Scraper] Error finding or uploading to file input (${fileInputSelector}):`, error);
             if (error.message && error.message.includes('File not found')) {
                 console.error(`[Scraper] Please ensure the image path is correct and accessible: ${imagePath}`);
             }
             throw new Error('Failed to upload file.');
        }

        console.log('[Scraper] Waiting for search results page to load after upload...');
        const resultsPageLoadSelector = 'div#search';
        let initialWaitSuccess = false;
        try {
            await page.waitForSelector(resultsPageLoadSelector, { visible: true, timeout: 5000 });
            console.log('[Scraper] Results container found on initial wait (within 5s). Page likely loaded.');
            initialWaitSuccess = true;
        } catch (error) {
            console.warn(`[Scraper] Initial wait for results container (${resultsPageLoadSelector}) failed within 5s. Assuming CAPTCHA or slow load.`);
            if (page) await page.screenshot({ path: 'error_screenshot_before_captcha_solve.png' });

            // *** Call the new direct API function ***
            const captchaToken = await handleCaptchaWith2CaptchaDirectAPI(page);

            if (!captchaToken) {
                // Error handling within handleCaptchaWith2CaptchaDirectAPI already logs details and takes screenshot
                throw new Error('Failed to solve CAPTCHA using direct API or results page did not load after attempt.');
            }

            console.log(`[Scraper] Direct API returned Token: ${captchaToken.substring(0,20)}... Injecting token.`);

            // Inject the token into the page
            await page.evaluate((token) => {
                const textarea = document.getElementById('g-recaptcha-response');
                if (textarea) textarea.value = token;
                // Optional: Attempt to find and click a submit button if needed, though often submission is automatic
                try {
                    const buttons = document.querySelectorAll('input[type="submit"], button[type="submit"], button:not([type]), input[type="button"]'); // Broader button selection
                    console.log(`Found ${buttons.length} potential submit buttons.`);
                    let clicked = false;
                    buttons.forEach(button => {
                        // Basic visibility check and avoid clicking multiple times
                        if (button.offsetParent !== null && !clicked) {
                           console.log(`Attempting to click button: ${button.outerHTML.substring(0, 100)}...`);
                           button.click();
                           clicked = true;
                        }
                    });
                    if (!clicked) {
                        console.log('No visible submit button found or clicked after token injection.');
                    }
                } catch (e) {
                     console.error('Error trying to click submit button:', e.message);
                }
            }, captchaToken);

            console.log('[Scraper] CAPTCHA token injected and submit attempted. Waiting longer for page to proceed after direct API solve...');
            await new Promise(resolve => setTimeout(resolve, 15000)); // Increased wait to 15 seconds

            console.log('[Scraper] Retrying to wait for results container after CAPTCHA attempt...');
            await page.waitForSelector(resultsPageLoadSelector, { visible: true, timeout: 20000 });
            console.log('[Scraper] Results container found after CAPTCHA solve attempt!');
            initialWaitSuccess = true;
        }

        if (!initialWaitSuccess) {
             console.error('[Scraper] Could not load results page even after CAPTCHA attempt (if any).');
             throw new Error('Results page did not load.');
        }

        console.log('[Scraper] Parsing results...');
        const resultsContainerSelector = 'div.srKDX.cvP2Ce';
        const linkSelector = 'a.LBcIee';
        try {
            console.log(`[Scraper] Looking for container (${resultsContainerSelector}) to extract links (${linkSelector}) from...`);
            const urls = await page.$$eval(
                resultsContainerSelector, 
                (containers, linkSel) => {
                    const hrefs = [];
                    for (const containerElem of containers) {
                        const anchors = containerElem.querySelectorAll(linkSel);
                        for (const a of anchors) {
                            if (a.href && a.href.startsWith('http')) {
                                try {
                                    const domain = new URL(a.href).hostname;
                                    if (!domain.includes('google.com') && 
                                        !domain.includes('google.co') && 
                                        !domain.includes('gstatic.com') &&
                                        !domain.includes('googleusercontent.com') &&
                                        !a.href.includes('/imgres') &&
                                        !a.href.includes('/search?')) {
                                        hrefs.push(a.href);
                                    }
                                } catch (urlError) {
                                    console.warn(`[Scraper] Skipping invalid URL in browser: ${a.href}`, urlError.message);
                                }
                            }
                        }
                    }
                    return hrefs;
                },
                linkSelector
            );
            
            const uniqueUrls = [...new Set(urls)];
            foundUrls.push(...uniqueUrls);
            console.log(`[Scraper] Found ${uniqueUrls.length} potential source URLs:`, uniqueUrls);

        } catch (error) {
            if (error.message.includes('failed to find element') || error.message.includes('waiting for selector')) {
                console.log(`[Scraper] Could not find results container or links using selectors: ${resultsContainerSelector} ${linkSelector}`);
            } else {
                console.error('[Scraper] Error parsing results:', error);
            }
        }
        console.log('[Scraper] Scraping finished.');
    } catch (error) {
        console.error('[Scraper] An error occurred during scraping:', error.message || error);
        if (browser && browser.isConnected() && page && !page.isClosed()) { 
            try {
                 await page.screenshot({ path: 'error_screenshot_scraping_failed.png' });
                 console.log('[Scraper] Debug screenshot saved to error_screenshot_scraping_failed.png');
            } catch (ssError) {
                 console.error('[Scraper] Could not save debug screenshot on final error:', ssError.message || ssError);
            }
        }
    } finally {
        if (browser && browser.isConnected()) { // Check if browser is still connected
            console.log('[Scraper] Closing browser...');
            await browser.close();
        }
    }
    return foundUrls;
}

// --- Test Section ---
async function runTest() {
    if (!captchApiKey) {
        console.error("\n--- Test run failed: TWOCAPTCHA_API_KEY environment variable is not set. ---");
        return;
    }
    const testImagePath = 'C:\\Github\\FindSourceURL\\data\\github.png';
    try {
        const urls = await findImageSourceUrls(testImagePath);
        if (urls.length > 0) {
            console.log('\n--- Found Source URLs ---');
            urls.forEach(url => console.log(url));
        } else {
            console.log('\n--- No source URLs found for this image. ---');
        }
    } catch (err) {
        console.error('\n--- Test run failed ---', err.message || err);
    }
}

// Ensure this is imagePath, not testImagePath if runTest is called from elsewhere
// For direct execution: 
if (require.main === module) { // Only run test if script is executed directly
    runTest(); 
}

module.exports = { findImageSourceUrls }; 