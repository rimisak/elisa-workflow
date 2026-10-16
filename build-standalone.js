#!/usr/bin/env node
// Builds ELISA-Workflow-App.html: index.html with vendor scripts and icon inlined,
// manifest and service worker dropped, so it works from one downloaded file.
const fs = require('fs');
const read = f => fs.readFileSync(f, 'utf8');
let html = read('index.html');
const swap = (re, fn) => { if (!re.test(html)) throw new Error('pattern not found: ' + re); html = html.replace(re, fn); };

swap(/<script src="(vendor\/[^"]+)"><\/script>/g, (_, p) =>
  '<script>' + read(p).replace(/<\/script/gi, '<\\/script') + '</script>');
swap(/<link rel="manifest"[^>]*>\n?/, '');
swap(/<link rel="icon" href="icon.svg"[^>]*>/, () =>
  '<link rel="icon" href="data:image/svg+xml;base64,' + Buffer.from(read('icon.svg')).toString('base64') + '" type="image/svg+xml">');
swap(/if\('serviceWorker' in navigator[\s\S]*?\n}\n/, '');

fs.writeFileSync('ELISA-Workflow-App.html', html);
console.log('Wrote ELISA-Workflow-App.html (' + (html.length / 1024).toFixed(0) + ' KB)');
