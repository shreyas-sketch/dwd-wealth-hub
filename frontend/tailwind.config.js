/** @type {import('tailwindcss').Config} */
// Coinzeye member app tokens live in src/index.css (--bz-* vars, light + dark).
// Token names are kept from Bullzeye so the copied components work unchanged.
module.exports = {
  darkMode: ["class"],
  content: ["./src/**/*.{js,jsx,ts,tsx}", "./public/index.html"],
  theme: {
    extend: {
      fontFamily: {
        // Ek Type (Mumbai) pair; both carry Devanagari for a later Hindi version.
        bz: ["Mukta", "-apple-system", "BlinkMacSystemFont", '"Segoe UI"', "sans-serif"],      // text + UI
        bzserif: ['"Baloo 2"', "Mukta", "system-ui", "sans-serif"],                          // display (name kept for old classes)
        bzdisplay: ['"Baloo 2"', "Mukta", "system-ui", "sans-serif"],
        bzmono: ['"JetBrains Mono"', "Menlo", "monospace"],                                  // admin / code only
      },
      boxShadow: {
        bzsheet: "0 -8px 32px rgba(27,31,74,0.16)",
        bzframe: "var(--card-shadow)",
      },
      borderRadius: {
        bzhero: "28px",   // the one hero panel
        bzcard: "20px",   // groups
        bzbtn: "12px",    // inputs, small boxes
      },
      colors: {
        bz: {
          bg: "var(--bz-bg)",
          panel: "var(--bz-panel)",
          card: "var(--bz-card)",
          ink: "var(--bz-ink)",
          muted: "var(--bz-muted)",
          line: "var(--bz-line)",
          "line-strong": "var(--bz-line-strong)",
          inset: "var(--bz-inset)",
          accent: "var(--bz-accent)",
          "accent-deep": "var(--bz-accent-deep)",
          "accent-tint": "var(--bz-accent-tint)",
          "on-accent": "var(--bz-on-accent)",
          miss: "var(--bz-miss)",
          "miss-tint": "var(--bz-miss-tint)",
          gold: "var(--bz-gold)",
          "gold-deep": "var(--bz-gold-deep)",
          "gold-tint": "var(--bz-gold-tint)",
          scrim: "var(--bz-scrim)",
          btn: "var(--bz-btn)",
          "on-btn": "var(--bz-on-btn)",
          hero: "var(--bz-hero)",
          "hero-ink": "var(--bz-hero-ink)",
          "hero-muted": "var(--bz-hero-muted)",
          "hero-line": "var(--bz-hero-line)",
        },
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
