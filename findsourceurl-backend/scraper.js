const puppeteer = require('puppeteer');
const { Solver } = require('@2captcha/captcha-solver'); // Import 2Captcha Solver

// Initialize 2Captcha Solver outside the function if API key is static
// Ensure TWOCAPTCHA_API_KEY is set as an environment variable
const captchApiKey = process.env.TWOCAPTCHA_API_KEY;
let captchaSolver;
if (captchApiKey) {
    captchaSolver = new Solver(captchApiKey);
    console.log('[Scraper] 2Captcha Solver initialized.');
} else {
    console.warn('[Scraper] WARNING: TWOCAPTCHA_API_KEY environment variable not set. CAPTCHA solving will be skipped.');
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

            if (!captchaSolver) {
                console.error('[Scraper] 2Captcha solver not initialized. Skipping CAPTCHA attempt.');
                throw new Error('Results page did not load (CAPTCHA suspected, solver not available).');
            }

            console.log('[Scraper] Attempting to solve CAPTCHA with 2Captcha...');
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

                if (!sitekey) {
                    console.error('[Scraper] CRITICAL: Could not automatically find reCAPTCHA sitekey. Cannot proceed with 2Captcha.');
                    throw new Error('Failed to find reCAPTCHA sitekey for 2Captcha.');
                }
                
                console.log(`[Scraper] Using pageUrl: ${pageUrl} and sitekey: ${sitekey}`);
                
                // Corrected parameters based on error message: pass parameters as an object.
                // Using property names based on Python SDK examples (`sitekey`, `url`)
                const result = await captchaSolver.recaptcha({
                    sitekey: sitekey, 
                    url: pageUrl // Changed from pageUrl as separate arg to url property in object
                    // We might still need other options depending on the captcha type, e.g.:
                    // version: 'v2', 
                    // action: 'some_action', 
                    // enterprise: 1,
                    // invisible: 1
                }); 
                const captchaToken = result.data;
                console.log(`[Scraper] 2Captcha request ID: ${result.id}, Token: ${captchaToken.substring(0,20)}...`);

                await page.evaluate((token) => {
                    const textarea = document.getElementById('g-recaptcha-response');
                    if (textarea) textarea.value = token;
                    // Attempt to find a submit button related to the captcha or a general form submit
                    // This is highly speculative
                    const buttons = document.querySelectorAll('input[type="submit"], button[type="submit"]');
                    let submitted = false;
                    buttons.forEach(button => {
                        // Check if the button is visible and potentially related to submitting the captcha/form
                        if (button.offsetParent !== null && !submitted) { // visible
                            // More specific checks could be added here (e.g. button text or nearby elements)
                            // For a Google /sorry page, the submission might be automatic after token, or a specific button.
                            // button.click(); 
                            // submitted = true;
                            // console.log('Attempted to click a submit button.');
                        }
                    });
                }, captchaToken);
                
                console.log('[Scraper] CAPTCHA token injected. Trying to submit or waiting for page to proceed...');
                await new Promise(resolve => setTimeout(resolve, 5000)); // Increased wait for JS to process

                console.log('[Scraper] Retrying to wait for results container after CAPTCHA attempt...');
                await page.waitForSelector(resultsPageLoadSelector, { visible: true, timeout: 20000 });
                console.log('[Scraper] Results container found after CAPTCHA solve attempt!');
                initialWaitSuccess = true;

            } catch (captchaError) {
                console.error('[Scraper] Error during 2Captcha solving process:', captchaError.message || captchaError);
                if(page) await page.screenshot({ path: 'error_screenshot_captcha_solve_failed.png' });
                throw new Error(`Failed to solve CAPTCHA or results page did not load after attempt: ${captchaError.message || captchaError}`);
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