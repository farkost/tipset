/**
 * Laddas före api-config.js. Om api-config misslyckas finns ändå vänliga felmeddelanden.
 */
(function () {
  if (typeof window.pasktipsetParseJsonResponse !== 'function') {
    window.pasktipsetParseJsonResponse = async function (res) {
      var t = await res.text();
      try {
        return JSON.parse(t);
      } catch (_) {
        return {};
      }
    };
  }
  if (typeof window.pasktipsetApiUnreachableMessage !== 'function') {
    window.pasktipsetApiUnreachableMessage = function () {
      var h =
        typeof location !== 'undefined' && location.hostname
          ? String(location.hostname).toLowerCase()
          : '';
      var local =
        h === '' || h === 'localhost' || h === '127.0.0.1' || h === '[::1]' || h === '::1';
      if (local) {
        return 'Ingen kontakt med servern. Starta python3 server.py i projektmappen eller be om hjälp.';
      }
      return 'Spelet kunde inte nå servern. Försök igen om en stund eller kontakta arrangören.';
    };
  }
})();
