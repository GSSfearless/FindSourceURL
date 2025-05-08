const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
puppeteer.use(StealthPlugin());
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
    let page = null;
    const foundUrls = [];

    try {
        browser = await puppeteer.launch({ 
            headless: false, 
            // slowMo: 50, // You can uncomment and adjust slowMo for visual debugging
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                // '--window-size=1366,768', // Setting viewport is usually enough
            ]
        });
        page = await browser.newPage();
        await page.setViewport({ width: 1366, height: 768 });
        // await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36'); // Example of a specific UA
        
        console.log('[Scraper] Navigating to Google Images...');
        try {
            await page.goto('https://images.google.com/', { waitUntil: 'networkidle0', timeout: 25000 });
            await page.waitForTimeout(2000); // Extra wait for dynamic content
        } catch (navError) {
            console.error('[Scraper] Error navigating to Google Images:', navError.message);
            if (page) await page.screenshot({ path: 'error_screenshot_navigation_failed.png' });
            throw new Error('Navigation to Google Images failed.');
        }

        console.log('[Scraper] Looking for camera icon...');
        const cameraIconSelector = 'div[aria-label="按图搜索"]'; // Aria label for Chinese UI
        // const cameraIconSelectorAlternate = 'div[aria-label="Search by image"]'; // For English UI, keep as a note
        try {
            await page.waitForSelector(cameraIconSelector, { visible: true, timeout: 20000 }); // Increased timeout
            await page.click(cameraIconSelector);
            console.log('[Scraper] Camera icon clicked.');
        } catch (error) {
            console.error(`[Scraper] Error finding or clicking camera icon (${cameraIconSelector}):`, error.message);
            if (page) {
                const currentUrl = page.url();
                console.log(`[Scraper] URL when camera icon not found: ${currentUrl}`);
                try {
                    const pageContent = await page.content();
                    console.log('[Scraper] Page content when camera icon not found (first 1000 chars):', pageContent.substring(0, 1000));
                    require('fs').writeFileSync('debug_page_content_camera_icon_failed.html', pageContent);
                    console.log('[Scraper] Full page content saved to debug_page_content_camera_icon_failed.html');
                } catch (contentError) {
                    console.error('[Scraper] Could not get page content when camera icon failed:', contentError.message);
                }
                await page.screenshot({ path: 'error_screenshot_camera_icon_failed.png' });
                console.log('[Scraper] Screenshot saved to error_screenshot_camera_icon_failed.png');
            }
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

            const captchaToken = await handleCaptchaWith2CaptchaDirectAPI(page);

            if (!captchaToken) {
                throw new Error('Failed to solve CAPTCHA using direct API.');
            }
            console.log(`[Scraper] Direct API returned Token: ${captchaToken.substring(0,20)}...`);

            const currentUrlAfterCaptchaSolve = page.url();
            console.log(`[Scraper] URL immediately after CAPTCHA solve: ${currentUrlAfterCaptchaSolve}`);

            if (currentUrlAfterCaptchaSolve.includes('/sorry/index')) {
                console.log('[Scraper] Confirmed on /sorry/index page. Attempting to reconstruct URL with token.');
                try {
                    const urlObject = new URL(currentUrlAfterCaptchaSolve);
                    const qParam = urlObject.searchParams.get('q');
                    const continueParam = urlObject.searchParams.get('continue');

                    if (qParam && continueParam) {
                        const newNavUrl = `https://www.google.com/sorry/index?q=${encodeURIComponent(qParam)}&continue=${encodeURIComponent(continueParam)}&g-recaptcha-response=${encodeURIComponent(captchaToken)}`;
                        console.log(`[Scraper] Constructed new navigation URL: ${newNavUrl.substring(0, 250)}...`);
                        await page.goto(newNavUrl, { waitUntil: 'networkidle2', timeout: 30000 });
                        console.log('[Scraper] Navigated to new reconstructed URL with token.');
                    } else {
                        console.warn('[Scraper] Could not extract q and continue parameters from /sorry/index URL. Fallback: Submitting on current page.');
                        await injectAndSubmitToken(page, captchaToken);
                    }
                } catch (urlParseError) {
                    console.error('[Scraper] Error parsing current URL or navigating to reconstructed URL. Fallback: Submitting on current page.', urlParseError);
                    await injectAndSubmitToken(page, captchaToken); 
                }
            } else {
                console.log(`[Scraper] Not on /sorry/index (URL: ${currentUrlAfterCaptchaSolve}). CAPTCHA was present. Fallback: Submitting on current page.`);
                await injectAndSubmitToken(page, captchaToken);
            }
            
            console.log('[Scraper] Retrying to wait for results container after CAPTCHA navigation/submission...');
            try {
                await page.waitForSelector(resultsPageLoadSelector, { visible: true, timeout: 20000 });
                console.log('[Scraper] Results container found after CAPTCHA solve attempt!');
                initialWaitSuccess = true;
            } catch (e_after_captcha) {
                console.error(`[Scraper] Still could not find results container (${resultsPageLoadSelector}) after CAPTCHA. Error: ${e_after_captcha.message}`);
                if (page) {
                    const currentUrl = page.url();
                    console.log(`[Scraper] Current page URL when div#search failed after captcha: ${currentUrl}`);
                    try {
                        const pageContent = await page.content();
                        console.log('[Scraper] Page content when div#search failed after captcha (first 2000 chars):', pageContent.substring(0, 2000));
                        // For full content, you might write it to a file if it's too long for console
                        // require('fs').writeFileSync('debug_page_content_after_captcha.html', pageContent);
                    } catch (contentError) {
                        console.error('[Scraper] Could not get page content after captcha failure:', contentError.message);
                    }
                    await page.screenshot({ path: 'error_screenshot_after_captcha_div_search_failed.png' });
                    console.log('[Scraper] Screenshot saved to error_screenshot_after_captcha_div_search_failed.png');
                }
                throw e_after_captcha; // Re-throw the error to be caught by the outer try-catch
            }
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

async function injectAndSubmitToken(page, token) {
    console.log(`[Scraper] Injecting token: ${token.substring(0,20)}... and attempting submit on current page.`);
    await page.evaluate((tk) => {
        const textarea = document.getElementById('g-recaptcha-response');
        if (textarea) textarea.value = tk;
        try {
            const buttons = document.querySelectorAll('input[type="submit"], button[type="submit"], button:not([type]), input[type="button"]');
            console.log(`Found ${buttons.length} potential submit buttons.`);
            let clicked = false;
            buttons.forEach(button => {
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
            console.error('Error trying to click submit button during injection:', e.message);
        }
    }, token);
    await new Promise(resolve => setTimeout(resolve, 15000)); // Wait for page to process
}

// --- Main Execution ---
async function main() {
    const imagePathArg = process.argv[2]; // Get image path from command line argument

    if (!imagePathArg) {
        console.error('[Scraper] Error: No image path provided via command line argument.');
        console.log('[Scraper] Usage: node scraper.js <path_to_image_file>');
        process.exit(1); // Exit with an error code
    }

    console.log(`[Scraper] Received image path from argument: ${imagePathArg}`);

    try {
        // Ensure the path is treated as absolute, or resolve it if it might be relative
        // For now, assuming api.js sends an absolute path. If issues persist, we might need path.resolve here.
        const urls = await findImageSourceUrls(imagePathArg);

        if (urls && urls.length > 0) {
            console.log('--- Found Source URLs ---');
            urls.forEach(url => console.log(url));
        } else {
            // findImageSourceUrls should handle its own "No source URLs found" message before this,
            // but as a fallback or if it throws before printing that.
            console.log('--- No source URLs found for this image. ---');
        }
        process.exit(0); // Success
    } catch (error) {
        console.error('[Scraper] Critical error during main execution:', error.message || error);
        // Ensure the specific "no URLs found" marker is printed on any critical failure
        // if it hasn't been printed by findImageSourceUrls already.
        // This helps api.js determine the outcome.
        if (!console.log.toString().includes('--- No source URLs found for this image. ---')) {
             console.log('--- No source URLs found for this image. ---');
        }
        process.exit(1); // Indicate failure
    }
}

// Call the main function to start the process
main();

// Remove or comment out any old test execution code, for example:
/*
async function runTest() {
    const testImagePath = 'C:\\Github\\FindSourceURL\\data\\github.png'; // Example of hardcoded path
    console.log(`[Scraper] Running test with image: ${testImagePath}`);
    try {
        const urls = await findImageSourceUrls(testImagePath);
        if (urls && urls.length > 0) {
            console.log('--- Found Source URLs ---');
            urls.forEach(url => console.log(url));
        } else {
            console.log('--- No source URLs found for this image. ---');
        }
    } catch (error) {
        console.error('[Scraper] Test run failed:', error);
        console.log('--- No source URLs found for this image. ---');
    }
}
// runTest(); // Ensure this is commented out or removed
*/

module.exports = { findImageSourceUrls }; 