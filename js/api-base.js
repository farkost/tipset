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

function pasktipsetIsLocalDevHost() {
  var h =
    typeof location !== 'undefined' && location.hostname
      ? String(location.hostname).toLowerCase()
      : '';
  return h === '' || h === 'localhost' || h === '127.0.0.1' || h === '[::1]' || h === '::1';
}

/** När API inte svarar: inga terminalkommandon på publik sida. */
function pasktipsetApiUnreachableMessage() {
  if (pasktipsetIsLocalDevHost()) {
    return 'Ingen kontakt med servern. Utveckling: starta python3 server.py i projektmappen, eller be om hjälp.';
  }
  return 'Spelet kunde inte nå servern. Försök igen om en stund eller kontakta arrangören.';
}

/** Parsar JSON även om servern returnerar HTML (t.ex. 404-sida). */
async function pasktipsetParseJsonResponse(res) {
  var t = await res.text();
  try {
    return JSON.parse(t);
  } catch (_) {
    return {};
  }
}
