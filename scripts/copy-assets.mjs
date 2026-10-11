import { copyFileSync, mkdirSync } from 'node:fs';
mkdirSync('public/assets', { recursive: true });
copyFileSync('node_modules/htmx.org/dist/htmx.min.js', 'public/assets/htmx.js');
