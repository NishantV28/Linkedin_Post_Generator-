const http = require('http');
const fs = require('fs');
const path = require('path');
const url = require('url');

const PORT = process.env.PORT || 8000;
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

// Initial Mock Databank State
let publishedReports = [
  {
    id: "RPT-8992-A",
    title: "Vulnerability Analysis: RAG Injection via Malformed Prompt Vectors",
    category: "VULNERABILITY",
    type: "vulnerability",
    timestamp: "2024-10-24 14:32:01Z",
    confidence: 98.4,
    status: "verified",
    summary: "Detailed advisory covering injection vectors in Retrieval-Augmented Generation architectures when unsanitized text feeds are embedded into context windows.",
    content: "## Overview\nThis vulnerability exploits soft attention boundaries in standard LLM embedding pipelines...\n\n### Impact\nUnrestricted context override and secondary prompt injection.\n\n### Mitigation\nImplement vector sanity sanitization before distance computation.",
    vectors: ["Vector-Alpha-4", "Vector-Gamma-1"],
    logs: [
      "14:30:00 [DISCOVERY] Ingesting prompt vectors from telemetry pipeline",
      "14:31:12 [ANALYSIS] Replicating prompt injection heuristic - Confirmed",
      "14:32:01 [SYNTHESIS] Article compiled with 98.4% confidence score"
    ]
  },
  {
    id: "RPT-8991-B",
    title: "Emerging Threat: Shadow AI API Gateway Bypass",
    category: "ADVISORY",
    type: "advisory",
    timestamp: "2024-10-24 11:15:44Z",
    confidence: 82.1,
    status: "warning",
    summary: "Analysis of unmonitored proxy gateways leaking enterprise secrets during autonomous tool calls.",
    content: "## Executive Summary\nShadow AI deployments present elevated data leak vectors across decentralized API gateways...",
    vectors: ["Vector-Beta-2"],
    logs: [
      "11:10:00 [DISCOVERY] Port scan metrics indicating unauthorized REST proxy",
      "11:15:44 [SYNTHESIS] Advisory published to security stream"
    ]
  },
  {
    id: "RPT-8988-A",
    title: "Solid-State Breakout vs Market Hesitation",
    category: "ANALYSIS",
    type: "analysis",
    timestamp: "2024-10-23 09:02:10Z",
    confidence: 95.6,
    status: "verified",
    summary: "Synthesis of recent patent filings against European battery manufacturer stock futures.",
    content: "## Market Synthesis\nSolid-state battery breakthroughs show strong technical validation but faces high initial capital deployment lag...",
    vectors: ["Vector-Delta-9", "Vector-Epsilon-3"],
    logs: [
      "09:00:00 [INGEST] Reddit & USPTO database cross-reference",
      "09:02:10 [PUBLISH] Report dispatched with high market correlation"
    ]
  }
];

let spikedTopics = [
  {
    id: "SPK-1042",
    title: "Quantum Annealing in Commercial Logistics",
    category: "Low Relevance",
    cause: "Topic density low, commercial viability unverified",
    timestamp: "10:42 AM - Today",
    node: "Node-Alpha-4",
    confidence: 42,
    heuristic: [
      "> WARN: Topic density low.",
      "> ERR: Commercial application unverified.",
      "> ACTION: SPIKE (Threshold < 60)"
    ],
    summary: "Analysis of D-Wave systems implementation for routing optimization lacking significant disruption potential."
  },
  {
    id: "SPK-1038",
    title: "CRISPR Off-Target Effects in Agriculture",
    category: "Redundant Data",
    cause: "Duplicates insights already published in Cycle 4.1.8",
    timestamp: "08:15 AM - Today",
    node: "Node-Beta-1",
    confidence: 88,
    heuristic: [
      "> MATCH: Similar record found (ID: C4.1.8-92).",
      "> INFO: Novelty score 0.12.",
      "> ACTION: SPIKE (Redundant)"
    ],
    summary: "Review of unintended genetic modifications in modified crop strains duplicating previous findings."
  },
  {
    id: "SPK-1020",
    title: "Deep-Sea Mining Ecological Impact Model",
    category: "Inconclusive Evidence",
    cause: "Insufficient data vectors, model variance > 80%",
    timestamp: "Yesterday - 23:59",
    node: "Node-Gamma-7",
    confidence: 12,
    purged: true,
    heuristic: [
      "> ERR: Insufficient data vectors.",
      "> WARN: Model variance > 80%.",
      "> ACTION: SPIKE (Inconclusive)"
    ],
    summary: "Simulation of sediment plume dispersion with incomplete sensor streams."
  }
];

let cycleLogs = [
  {
    id: "CYC-9482.RUN",
    timestamp: new Date().toISOString(),
    status: "RUNNING",
    headline: "Initiating deep scan across 14 primary data vectors.",
    details: [
      "[SYS] Allocating secondary computational nodes... [OK]",
      "[NET] Establishing secure stream to global ingest... [OK]",
      "_ Scanning cluster beta-9 (45% complete)"
    ]
  },
  {
    id: "CYC-9481.CMP",
    timestamp: new Date(Date.now() - 15 * 60 * 1000).toISOString(),
    status: "COMPLETE",
    headline: "Scanned 42 sources, identified 3 potential vectors.",
    details: [
      "- Vector Alpha mapped to target demographic profile.",
      "- Vector Gamma requires secondary verification (queued).",
      "- Cycle closed normally. Duration: 1m 45s."
    ]
  },
  {
    id: "CYC-9480.CMP",
    timestamp: new Date(Date.now() - 45 * 60 * 1000).toISOString(),
    status: "COMPLETE",
    headline: "Routine synchronization with remote node Alpha-7.",
    details: [
      "- Node synchronization complete.",
      "- No discrepancies detected."
    ]
  },
  {
    id: "CYC-9479.ERR",
    timestamp: new Date(Date.now() - 120 * 60 * 1000).toISOString(),
    status: "FAILED",
    headline: "Attempted to parse encrypted payload from unknown source.",
    details: [
      "[ERR] Decryption protocol mismatch. Handshake rejected.",
      "[SYS] Terminating cycle to prevent cascade failure.",
      "[LOG] Core dumped to /var/log/ada/crash_9479.dmp"
    ]
  }
];

const feedLines = [
  { tag: "DISCOVERY", tagColor: "text-primary", text: "Ingesting sub-reddit /r/technology trend spikes regarding new solid-state battery tech." },
  { tag: "ANALYSIS", tagColor: "text-secondary", text: "Cross-referencing claims with recent patent filings in USPTO database. 3 matches found." },
  { tag: "DISCOVERY", tagColor: "text-primary", text: "Sentiment shift detected in European market futures concerning tech sector." },
  { tag: "DRAFTING", tagColor: "text-tertiary", text: "Initiating preliminary article framework: \"Solid-State Breakout vs Market Hesitation\". Contextual depth: Deep." },
  { tag: "ANALYSIS", tagColor: "text-secondary", text: "Running bias-check heuristic on draft section 1. Score: 0.04 (Neutral)." },
  { tag: "DISCOVERY", tagColor: "text-primary", text: "New CVE disclosure indexed. Cross-checking against tracked vendor list." },
  { tag: "SYNTHESIS", tagColor: "text-secondary", text: "Merging vector clusters Alpha-4 and Gamma-7 into unified narrative draft." },
  { tag: "ANALYSIS", tagColor: "text-secondary", text: "Confidence threshold recalibrated for geopolitics vertical. New floor: 62%." }
];

function jsonResponse(res, statusCode, data) {
  res.writeHead(statusCode, {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization'
  });
  res.end(JSON.stringify(data));
}

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

  // Handle REST API Endpoints
  if (pathname.startsWith('/api/')) {
    if (pathname === '/api/status' && req.method === 'GET') {
      return jsonResponse(res, 200, {
        status: "ONLINE",
        version: "v4.2.0-Active",
        metrics: {
          compute: "78%",
          apiCalls: "24k/s",
          memory: "12GB",
          publishRate: "4.2%",
          cadence: "~150 min",
          articles24h: 142 + publishedReports.length - 3,
          accuracy: "99.8%"
        }
      });
    }

    if (pathname === '/api/agent/init' && req.method === 'POST') {
      let body = '';
      req.on('data', chunk => body += chunk);
      req.on('end', () => {
        const cycleId = `CYC-${Math.floor(1000 + Math.random() * 9000)}.RUN`;
        const newCycle = {
          id: cycleId,
          timestamp: new Date().toISOString(),
          status: "RUNNING",
          headline: "Autonomous cycle initiated via API command.",
          details: [
            "[SYS] Allocating GPU clusters... [OK]",
            "[NET] Connecting to broad spectrum ingestion feed... [OK]",
            "_ Ingesting & processing vectors..."
          ]
        };
        cycleLogs.unshift(newCycle);

        return jsonResponse(res, 200, {
          status: "initialized",
          instance_id: `agt_${Math.random().toString(36).substring(2, 8)}`,
          cycle_id: cycleId,
          timestamp: new Date().toISOString()
        });
      });
      return;
    }

    if (pathname === '/api/agent/feed' && req.method === 'GET') {
      return jsonResponse(res, 200, {
        feed: feedLines,
        timestamp: new Date().toISOString()
      });
    }

    if (pathname === '/api/reports/published' && req.method === 'GET') {
      return jsonResponse(res, 200, publishedReports);
    }

    if (pathname === '/api/reports/spiked' && req.method === 'GET') {
      return jsonResponse(res, 200, spikedTopics);
    }

    if (pathname === '/api/cycles' && req.method === 'GET') {
      return jsonResponse(res, 200, cycleLogs);
    }

    if (pathname === '/api/reports/spiked/reevaluate' && req.method === 'POST') {
      let body = '';
      req.on('data', chunk => body += chunk);
      req.on('end', () => {
        try {
          const parsed = JSON.parse(body || '{}');
          const item = spikedTopics.find(s => s.id === parsed.id);
          if (item) {
            item.confidence = Math.min(99, item.confidence + 35);
            if (item.confidence >= 70) {
              // Promote to published
              const newPublished = {
                id: `RPT-${Math.floor(8000 + Math.random() * 1000)}-RE`,
                title: item.title,
                category: "RE-EVALUATED",
                type: "analysis",
                timestamp: new Date().toISOString(),
                confidence: item.confidence,
                status: "verified",
                summary: item.summary,
                content: `## Re-Evaluated Advisory\n${item.summary}\n\nPromoted after confidence score re-calculation.`,
                vectors: [item.node],
                logs: item.heuristic
              };
              publishedReports.unshift(newPublished);
            }
          }
          return jsonResponse(res, 200, { success: true, item });
        } catch (e) {
          return jsonResponse(res, 400, { error: e.message });
        }
      });
      return;
    }

    return jsonResponse(res, 404, { error: "API route not found" });
  }

  // Handle Static File Requests
  if (pathname === '/') {
    pathname = '/index.html';
  }

  let filePath = path.join(PUBLIC_DIR, pathname);
  const ext = path.extname(filePath).toLowerCase();

  fs.stat(filePath, (err, stats) => {
    if (err || !stats.isFile()) {
      res.writeHead(404, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end('<h1>404 Not Found</h1><p>The requested path does not exist on Ada Desk server.</p>');
      return;
    }

    const contentType = MIME_TYPES[ext] || 'application/octet-stream';
    res.writeHead(200, { 'Content-Type': contentType });
    fs.createReadStream(filePath).pipe(res);
  });
});

server.listen(PORT, () => {
  console.log(`\n==================================================`);
  console.log(`  Ada Engine Dashboard running at http://localhost:${PORT}`);
  console.log(`  Static & API Backend Ready!`);
  console.log(`==================================================\n`);
});
