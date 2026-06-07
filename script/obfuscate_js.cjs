/**
 * JS Obfuscation Build Script
 *
 * Reads source files from static/js/ and outputs obfuscated versions
 * to static/js-dist/. Run before deployment:
 *   node script/obfuscate_js.cjs
 *
 * Restore source readability during development:
 *   git checkout website/static/js/
 */
const fs = require('fs');
const path = require('path');
const JavaScriptObfuscator = require('javascript-obfuscator');

const SRC_DIR = path.join(__dirname, '..', 'website', 'static', 'js');
const DIST_DIR = path.join(__dirname, '..', 'website', 'static', 'js-dist');

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

// ── Ensure dist directory exists ─────────────────────────────────────────
if (!fs.existsSync(DIST_DIR)) {
  fs.mkdirSync(DIST_DIR, { recursive: true });
}

// ── Find all .js files ───────────────────────────────────────────────────
const files = fs.readdirSync(SRC_DIR).filter(f => f.endsWith('.js'));

if (files.length === 0) {
  console.log('No JS files found in', SRC_DIR);
  process.exit(0);
}

console.log(`Obfuscating ${files.length} file(s)...\n`);

let totalOriginal = 0;
let totalObfuscated = 0;

for (const file of files) {
  const srcPath = path.join(SRC_DIR, file);
  const srcCode = fs.readFileSync(srcPath, 'utf-8');
  const originalSize = Buffer.byteLength(srcCode, 'utf-8');

  try {
    const result = JavaScriptObfuscator.obfuscate(srcCode, {
      ...OPTIONS,
      // Per-file adjustments
      ...(file === 'tracker.js' ? { deadCodeInjection: false } : {}),
    });

    const obfuscated = result.getObfuscatedCode();
    const distPath = path.join(DIST_DIR, file);
    fs.writeFileSync(distPath, obfuscated, 'utf-8');

    const obfSize = Buffer.byteLength(obfuscated, 'utf-8');
    const ratio = ((obfSize / originalSize) * 100).toFixed(0);

    console.log(`  ${file}: ${(originalSize/1024).toFixed(1)}KB → ${(obfSize/1024).toFixed(1)}KB (${ratio}%)`);

    totalOriginal += originalSize;
    totalObfuscated += obfSize;
  } catch (err) {
    console.error(`  ${file}: ERROR - ${err.message}`);
  }
}

const totalRatio = ((totalObfuscated / totalOriginal) * 100).toFixed(0);
console.log(`\nDone: ${(totalOriginal/1024).toFixed(1)}KB → ${(totalObfuscated/1024).toFixed(1)}KB (${totalRatio}%)`);
