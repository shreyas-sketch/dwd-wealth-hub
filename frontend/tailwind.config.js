/** @type {import('tailwindcss').Config} */
// Coinzeye member app tokens live in src/index.css (--bz-* vars, light + dark).
// Token names are kept from Bullzeye so the copied components work unchanged.
module.exports = {
  darkMode: ["class"],
  content: ["./src/**/*.{js,jsx,ts,tsx}", "./public/index.html"],
  theme: {
    extend: {
      fontFamily: {
        bz: ["Inter", "-apple-system", "BlinkMacSystemFont", '"Segoe UI"', "sans-serif"],
        bzmono: ['"JetBrains Mono"', "Menlo", "monospace"],
        bzserif: ["Fraunces", '"Playfair Display"', "Georgia", "serif"],
      },
      boxShadow: {
        bzsheet: "0 -8px 32px rgba(20,24,33,0.14)",
        bzframe: "var(--card-shadow)",
      },
      borderRadius: {
        bzcard: "16px",
        bzbtn: "10px",
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
        },
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
