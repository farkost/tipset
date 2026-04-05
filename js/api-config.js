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
