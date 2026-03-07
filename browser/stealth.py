"""Stealth JavaScript injection scripts for anti-bot evasion."""

STEALTH_SCRIPT = """
    // Hide webdriver
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    // Overwrite plugins
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    // Overwrite languages
    Object.defineProperty(navigator, 'languages', {
        get: () => ['zh-CN', 'zh', 'en-US', 'en', 'ja']
    });
    // Add chrome runtime
    Object.defineProperty(navigator, 'chrome', { get: () => ({ runtime: {} }) });
    // Override permissions query
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
            Promise.resolve({ state: Notification.permission }) :
            originalQuery(parameters)
    );
    // Mock screen
    window.screen = {
        availHeight: 1080, availLeft: 0, availTop: 0, availWidth: 1920,
        colorDepth: 24, height: 1080, isExtended: true, onchange: null,
        orientation: { angle: 0, type: 'landscape-primary' },
        pixelDepth: 24, width: 1920
    };
    if (!window.navigator.permissions) {
        window.navigator.permissions = {
            query: () => Promise.resolve({ state: 'prompt' })
        };
    }
    if (!window.chrome) {
        window.chrome = { csi: () => ({}), loadTimes: () => ({}), app: {} };
    }
    window.navigator.webdriver = false;
"""

ADVANCED_STEALTH_SCRIPT = """
    // Extra hardware/memory mocking
    Object.defineProperty(navigator, 'hardwareConcurrency', {
        get: () => 8, configurable: true
    });
    Object.defineProperty(navigator, 'deviceMemory', {
        get: () => 16, configurable: true
    });

    // Clean up web driver leakage
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;

    // Advanced canvas noise
    const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function(...args) {
        const context = this.getContext('2d');
        if (context && this.width > 0 && this.height > 0) {
            const tempCanvas = document.createElement('canvas');
            tempCanvas.width = this.width;
            tempCanvas.height = this.height;
            const tempCtx = tempCanvas.getContext('2d');
            tempCtx.drawImage(this, 0, 0);
            const imageData = tempCtx.getImageData(0, 0, this.width, this.height);
            const noisePixels = Math.min(10, Math.floor(imageData.data.length / 400));
            for (let i = 0; i < noisePixels; i++) {
                const idx = Math.floor(Math.random() * (imageData.data.length / 4)) * 4;
                if (imageData.data[idx] < 255) imageData.data[idx] += 1;
            }
            tempCtx.putImageData(imageData, 0, 0);
            return originalToDataURL.apply(tempCanvas, args);
        }
        return originalToDataURL.apply(this, args);
    };

    // WebGL Vendor spoofing
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
        if (parameter === 37445) return 'Intel Inc.';
        if (parameter === 37446) return 'Intel Iris OpenGL Engine';
        return getParameter.apply(this, arguments);
    };
"""
