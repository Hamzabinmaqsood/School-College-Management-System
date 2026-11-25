import { createReadStream } from 'node:fs';
import { stat } from 'node:fs/promises';
import { createServer, request } from 'node:http';
import { extname, resolve, sep } from 'node:path';

const root = resolve('frontend/dist/school/browser');
const mime = { '.css': 'text/css', '.js': 'text/javascript', '.woff2': 'font/woff2' };

createServer(async (incoming, outgoing) => {
  const url = new URL(incoming.url, 'http://localhost');
  if (url.pathname.startsWith('/api/')) {
    const upstream = request({
      hostname: '127.0.0.1',
      port: Number(process.env.DJANGO_PORT),
      path: incoming.url,
      method: incoming.method,
      headers: incoming.headers,
      agent: false,
    }, response => {
      outgoing.writeHead(response.statusCode, response.headers);
      response.pipe(outgoing);
    });
    upstream.on('error', () => outgoing.writeHead(502).end());
    incoming.pipe(upstream);
    return;
  }

  const candidate = resolve(root, '.' + url.pathname);
  const isAsset = candidate.startsWith(root + sep) && (await stat(candidate).catch(() => null))?.isFile();
  const file = isAsset ? candidate : resolve(root, 'index.html');
  const type = isAsset ? (mime[extname(file)] ?? 'application/octet-stream') : 'text/html';
  outgoing.writeHead(200, { 'Content-Type': type });
  createReadStream(file).on('error', () => outgoing.destroy()).pipe(outgoing);
}).listen(Number(process.env.ANGULAR_PORT), '127.0.0.1');
