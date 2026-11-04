// craco.config.js — Coinzeye web build (adapted from Bullzeye; no Solana/Raydium polyfills).
const path = require("path");

module.exports = {
  eslint: {
    configure: {
      extends: ["plugin:react-hooks/recommended"],
      rules: {
        "react-hooks/rules-of-hooks": "error",
        "react-hooks/exhaustive-deps": "warn",
      },
    },
  },
  webpack: {
    alias: { "@": path.resolve(__dirname, "src") },
    configure: (webpackConfig) => {
      webpackConfig.ignoreWarnings = [...(webpackConfig.ignoreWarnings || []), /Failed to parse source map/];
      webpackConfig.watchOptions = {
        ...webpackConfig.watchOptions,
        ignored: ["**/node_modules/**", "**/.git/**", "**/build/**", "**/public/**"],
      };
      return webpackConfig;
    },
  },
  // Local dev: `yarn start` on :3000 proxies /api to the backend on :8001.
  devServer: (cfg) => ({
    ...cfg,
    proxy: [{ context: ["/api"], target: process.env.DEV_API_TARGET || "http://localhost:8001" }],
  }),
};
