const http = require('http');
const fs = require('fs');
const path = require('path');
const url = require('url');

// FastAPI owns port 8000; keep the dashboard separate to avoid a port clash.
const PORT = process.env.PORT || 5173;
const PUBLIC_DIR = __dirname;

const MIME_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.otf': 'font/otf'
};

// Proxy API requests to FastAPI backend running on port 8000
const FASTAPI_TARGET = process.env.BACKEND_URL || 'http://127.0.0.1:8000';

const server = http.createServer((req, res) => {
  const parsedUrl = url.parse(req.url, true);
  let pathname = parsedUrl.pathname;

  // Enable CORS Preflight
  if (req.method === 'OPTIONS') {
    res.writeHead(204, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization'
    });
    res.end();
    return;
  }

  // Forward API / Health requests to FastAPI backend
  if (pathname.startsWith('/api/') || pathname === '/health') {
    const targetUrl = new url.URL(req.url, FASTAPI_TARGET);
    const proxyReq = http.request(targetUrl, {
      method: req.method,
      headers: {
        ...req.headers,
        host: targetUrl.host
      }
    }, (proxyRes) => {
      res.writeHead(proxyRes.statusCode, {
        ...proxyRes.headers,
        'Access-Control-Allow-Origin': '*'
      });
      proxyRes.pipe(res);
    });

    proxyReq.on('error', (err) => {
      res.writeHead(502, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: "FastAPI backend unreachable at " + FASTAPI_TARGET, detail: err.message }));
    });

    req.pipe(proxyReq);
    return;
  }

  // Handle Static File Requests
  if (pathname === '/') {
    pathname = '/welcome.html';
  }

  let filePath = path.join(PUBLIC_DIR, pathname);
  const ext = path.extname(filePath).toLowerCase();

  fs.stat(filePath, (err, stats) => {
    if (err || !stats.isFile()) {
      res.writeHead(404, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end('<h1>404 Not Found</h1><p>The requested path does not exist on Distill server.</p>');
      return;
    }

    const contentType = MIME_TYPES[ext] || 'application/octet-stream';
    res.writeHead(200, { 'Content-Type': contentType });
    fs.createReadStream(filePath).pipe(res);
  });
});

server.listen(PORT, () => {
  console.log(`\n==================================================`);
  console.log(`  Distill Dashboard running at http://localhost:${PORT}`);
  console.log(`  Static & API Backend Ready!`);
  console.log(`==================================================\n`);
});
