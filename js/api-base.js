/**
 * Bas-URL till Flask-API. Tom = samma origin som sidan (lokal utveckling eller API på samma domän).
 * På GitHub Pages: sätt window.__PASKTIPSET_API_BASE__ i en inline <script> före denna fil,
 * t.ex. till din backend: 'https://min-api.railway.app'
 */
(function () {
  var b = typeof window.__PASKTIPSET_API_BASE__ === 'string' ? window.__PASKTIPSET_API_BASE__.trim() : '';
  if (b.length && b.charAt(b.length - 1) === '/') b = b.slice(0, -1);
  window.__PASKTIPSET_API_BASE__ = b;
})();
function apiUrl(path) {
  var p = path || '';
  if (p.charAt(0) !== '/') p = '/' + p;
  return (window.__PASKTIPSET_API_BASE__ || '') + p;
}
