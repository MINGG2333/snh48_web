/**
 * JS Obfuscation + CSS Minification Build Script
 *
 * JS:  src=static/js/ → dist=static/js-dist/
 * CSS: src=static/css/ → dist=static/css-dist/
 *
 * Run before deployment:
 *   node script/obfuscate_js.cjs
 */
const fs = require('fs');
const path = require('path');
const JavaScriptObfuscator = require('javascript-obfuscator');
const CleanCSS = require('clean-css');

const BASE = path.join(__dirname, '..', 'website', 'static');
const JS_SRC = path.join(BASE, 'js');
const JS_DIST = path.join(BASE, 'js-dist');
const CSS_SRC_DIR = path.join(BASE, 'css');
const CSS_DIST_DIR = path.join(BASE, 'css-dist');

// ── Obfuscation options ──────────────────────────────────────────────────
const OPTIONS = {
  compact: true,
  controlFlowFlattening: true,
  controlFlowFlatteningThreshold: 0.75,
  deadCodeInjection: true,
  deadCodeInjectionThreshold: 0.3,
  identifierNamesGenerator: 'hexadecimal',
  renameGlobals: false,       // keep global names intact (needed for cross-file calls)
  selfDefending: false,        // set true for anti-tampering (but may break some tools)
  splitStrings: true,
  splitStringsChunkLength: 8,
  stringArray: true,
  stringArrayEncoding: ['base64'],
  stringArrayThreshold: 0.75,
  target: 'browser',
  // Preserve specific names that must not be renamed
  reservedNames: [
    '__QA_CONFIG__', 'SITE_DOMAIN', 'window', 'document',
    '_trackEvent', 'highlightCJY', 'sessionStorage',
  ],
  reservedStrings: [],
};

// ── Ensure dist directories exist ──────────────────────────────────────────
[JS_DIST, CSS_DIST_DIR].forEach(d => {
  if (!fs.existsSync(d)) fs.mkdirSync(d, { recursive: true });
});

// ═══════════════════════════════════════════════════════════════════════════
//  JS Obfuscation
// ═══════════════════════════════════════════════════════════════════════════

const jsFiles = fs.readdirSync(JS_SRC).filter(f => f.endsWith('.js'));

if (jsFiles.length === 0) {
  console.log('No JS files found in', JS_SRC);
} else {
  console.log(`Obfuscating ${jsFiles.length} JS file(s)...\n`);

  let totalOriginal = 0;
  let totalObfuscated = 0;

  for (const file of jsFiles) {
    const srcPath = path.join(JS_SRC, file);
    const srcCode = fs.readFileSync(srcPath, 'utf-8');
    const originalSize = Buffer.byteLength(srcCode, 'utf-8');

    try {
      const result = JavaScriptObfuscator.obfuscate(srcCode, {
        ...OPTIONS,
        ...(file === 'tracker.js' ? { deadCodeInjection: false } : {}),
      });

      const obfuscated = result.getObfuscatedCode();
      const distPath = path.join(JS_DIST, file);
      fs.writeFileSync(distPath, obfuscated, 'utf-8');

      const obfSize = Buffer.byteLength(obfuscated, 'utf-8');
      const ratio = ((obfSize / originalSize) * 100).toFixed(0);
      console.log(`  JS  ${file}: ${(originalSize/1024).toFixed(1)}KB → ${(obfSize/1024).toFixed(1)}KB (${ratio}%)`);

      totalOriginal += originalSize;
      totalObfuscated += obfSize;
    } catch (err) {
      console.error(`  JS  ${file}: ERROR - ${err.message}`);
    }
  }

  const totalRatio = ((totalObfuscated / totalOriginal) * 100).toFixed(0);
  console.log(`\nJS Done: ${(totalOriginal/1024).toFixed(1)}KB → ${(totalObfuscated/1024).toFixed(1)}KB (${totalRatio}%)\n`);
}

// ═══════════════════════════════════════════════════════════════════════════
//  CSS Minification
// ═══════════════════════════════════════════════════════════════════════════

const cssFiles = fs.readdirSync(CSS_SRC_DIR).filter(f => f.endsWith('.css'));

if (cssFiles.length === 0) {
  console.log('No CSS files found in', CSS_SRC_DIR);
} else {
  console.log(`Minifying ${cssFiles.length} CSS file(s)...\n`);
  const minifier = new CleanCSS({ level: 2 });

  let cssTotalOriginal = 0;
  let cssTotalMinified = 0;

  for (const file of cssFiles) {
    const srcPath = path.join(CSS_SRC_DIR, file);
    const srcCode = fs.readFileSync(srcPath, 'utf-8');
    const originalSize = Buffer.byteLength(srcCode, 'utf-8');

    const result = minifier.minify(srcCode);
    if (result.errors.length > 0) {
      console.error(`  CSS ${file}: ERROR - ${result.errors.join('; ')}`);
      continue;
    }

    const distPath = path.join(CSS_DIST_DIR, file);
    fs.writeFileSync(distPath, result.styles, 'utf-8');

    const minSize = Buffer.byteLength(result.styles, 'utf-8');
    const ratio = ((minSize / originalSize) * 100).toFixed(0);
    console.log(`  CSS ${file}: ${(originalSize/1024).toFixed(1)}KB → ${(minSize/1024).toFixed(1)}KB (${ratio}%)`);

    cssTotalOriginal += originalSize;
    cssTotalMinified += minSize;
  }

  const cssRatio = ((cssTotalMinified / cssTotalOriginal) * 100).toFixed(0);
  console.log(`\nCSS Done: ${(cssTotalOriginal/1024).toFixed(1)}KB → ${(cssTotalMinified/1024).toFixed(1)}KB (${cssRatio}%)`);
}

console.log('\n✅ Build complete.');
