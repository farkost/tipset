/**
 * Backend (Flask) — måste vara satt om sidan ligger på GitHub Pages.
 * Tom sträng = API anropas på samma adress som sidan (fungerar med python3 server.py lokalt).
 * Exempel: 'https://min-app.up.railway.app' (utan avslutande snedstreck).
 * Utan korrekt URL här fungerar inte skapa lobby / spela mot den publika sidan.
 */
window.__PASKTIPSET_API_BASE__ = '';

/**
 * Bas-URL till den publika webbplatsen (samma för alla), med avslutande snedstreck.
 * Vid lokal utveckling (localhost) används denna för länkar/QR i "Skapa spår" så deltagare får rätt adress.
 * På den publika sidan lämnas den tom — sidan använder då sin egen adress automatiskt.
 */
window.PASKTIPSET_PUBLIC_SITE_URL = 'https://farkost.github.io/tipset/';

/** Måste ligga här (före api-base.js) så funktionerna alltid finns även om annat skript misslyckas. */
window.pasktipsetIsLocalDevHost = function () {
  var h =
    typeof location !== 'undefined' && location.hostname
      ? String(location.hostname).toLowerCase()
      : '';
  return h === '' || h === 'localhost' || h === '127.0.0.1' || h === '[::1]' || h === '::1';
};

window.pasktipsetApiUnreachableMessage = function () {
  if (window.pasktipsetIsLocalDevHost()) {
    return 'Ingen kontakt med servern. Utveckling: starta python3 server.py i projektmappen, eller be om hjälp.';
  }
  if (!window.__PASKTIPSET_API_BASE__) {
    return 'Spelet är inte uppkopplat mot servern än. Kontakta den som har lagt ut sidan.';
  }
  return 'Spelet kunde inte nå servern. Försök igen om en stund eller kontakta arrangören.';
};

window.pasktipsetParseJsonResponse = async function (res) {
  var t = await res.text();
  try {
    return JSON.parse(t);
  } catch (_) {
    return {};
  }
};
