#!/usr/bin/env node
/**
 * Anti-bot challenge solver for zujuan.xkw.com
 *
 * Usage: node solve_challenge.js <html_file>
 *   OR: echo "<html>..." | node solve_challenge.js --stdin
 *
 * Executes the obfuscated JS from the challenge page in a JSDOM
 * environment and outputs the resulting cookies as JSON.
 */

const fs = require('fs');
const { JSDOM } = require('jsdom');

async function solveChallenge(html, targetUrl) {
  return new Promise((resolve, reject) => {
    try {
      const dom = new JSDOM(html, {
        url: targetUrl || 'https://zujuan.xkw.com/',
        referrer: 'https://zujuan.xkw.com/',
        contentType: 'text/html',
        runScripts: 'dangerously',
        resources: 'usable',
        pretendToBeVisual: true,
      });

      // Handle the "navigation to another Document" error
      dom.window.addEventListener('error', (event) => {
        // Suppress navigation errors
        if (event.message && event.message.includes('navigation')) {
          event.preventDefault();
          return;
        }
      });

      // Wait a moment for scripts to execute, then capture cookies
      setTimeout(async () => {
        try {
          // The script sets document.cookie, capture via cookieJar
          const cookies = [];
          const rawCookies = dom.window.document.cookie;

          if (rawCookies) {
            rawCookies.split(';').forEach(c => {
              const parts = c.trim().split('=');
              if (parts.length >= 2) {
                // Handle URL-encoded values properly
                cookies.push({
                  name: parts[0].trim(),
                  value: decodeURIComponent(parts.slice(1).join('=').trim()),
                  raw: parts.slice(1).join('=').trim(),
                });
              }
            });
          }

          // Also try getting cookies from the cookie jar
          try {
            const jarCookies = await dom.cookieJar.getCookies(targetUrl || 'https://zujuan.xkw.com/');
            jarCookies.forEach(c => {
              const exists = cookies.find(ck => ck.name === c.key);
              if (!exists) {
                cookies.push({ name: c.key, value: c.value, raw: c.value });
              }
            });
          } catch (e) {
            // cookieJar might not be available
          }

          const result = {};
          cookies.forEach(c => {
            result[c.name] = c.raw || c.value;
          });

          dom.window.close();
          resolve(result);
        } catch (e) {
          reject(e);
        }
      }, 1000);
    } catch (e) {
      reject(e);
    }
  });
}

async function main() {
  let html, targetUrl;

  if (process.argv.includes('--stdin')) {
    // Read HTML from stdin (sync for subprocess compatibility)
    html = fs.readFileSync(process.stdin.fd, 'utf-8');
    targetUrl = process.argv[process.argv.length - 1];
    if (targetUrl === '--stdin') targetUrl = 'https://zujuan.xkw.com/';
  } else if (process.argv[2]) {
    const path = process.argv[2];
    if (fs.existsSync(path)) {
      html = fs.readFileSync(path, 'utf-8');
    } else {
      // Treat as URL
      console.error('Fetching not supported directly. Pipe HTML via --stdin.');
      process.exit(1);
    }
    targetUrl = process.argv[3] || 'https://zujuan.xkw.com/';
  } else {
    console.error('Usage: node solve_challenge.js <html_file> [url]');
    console.error('   or: echo "<html>" | node solve_challenge.js --stdin [url]');
    process.exit(1);
  }

  if (!html.includes('hash32') || !html.includes('parm_0')) {
    console.error('Not a challenge page');
    console.log('{}');
    return;
  }

  console.error(`HTML size: ${html.length} bytes`);
  const cookies = await solveChallenge(html, targetUrl);
  console.error(`Solved: ${JSON.stringify(cookies)}`);
  console.log(JSON.stringify(cookies));
}

main().catch(err => {
  console.error('Error:', err.message);
  // Return empty JSON
  console.log('{}');
});
