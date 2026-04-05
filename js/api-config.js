/** Om frontend (t.ex. GitHub Pages) och API ligger på olika adresser: sätt backend-URL här, utan avslutande snedstreck. */
window.__PASKTIPSET_API_BASE__ = '';

/**
 * Bas-URL till den publika webbplatsen (samma för alla), med avslutande snedstreck.
 * Vid lokal utveckling (localhost) används denna för länkar/QR i "Skapa spår" så deltagare får rätt adress.
 * På den publika sidan lämnas den tom — sidan använder då sin egen adress automatiskt.
 */
window.PASKTIPSET_PUBLIC_SITE_URL = 'https://farkost.github.io/tipset/';
