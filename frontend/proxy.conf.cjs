const port = Number(process.env.DJANGO_PORT || 8000);
if (!Number.isInteger(port) || port < 1 || port > 65535) {
  throw new Error('DJANGO_PORT must be between 1 and 65535');
}

module.exports = {
  '/api/**': {target: 'http://127.0.0.1:' + port, changeOrigin: false},
};
