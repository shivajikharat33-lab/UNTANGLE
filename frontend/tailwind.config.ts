import type { Config } from "tailwindcss";

/**
 * Light-theme tokens. A later dark theme overrides the CSS variables in
 * src/index.css under [data-theme="dark"] without renaming these keys.
 */
const config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "rgb(var(--paper) / <alpha-value>)",
        "paper-raised": "rgb(var(--paper-raised) / <alpha-value>)",
        ink: "rgb(var(--ink) / <alpha-value>)",
        "ink-soft": "rgb(var(--ink-soft) / <alpha-value>)",
        copper: "rgb(var(--copper) / <alpha-value>)",
        "copper-deep": "rgb(var(--copper-deep) / <alpha-value>)",
        line: "rgb(var(--line) / <alpha-value>)",
        nav: "rgb(var(--nav) / <alpha-value>)",
        "nav-text": "rgb(var(--nav-text) / <alpha-value>)",
        "nav-muted": "rgb(var(--nav-muted) / <alpha-value>)",
        teal: "rgb(var(--teal) / <alpha-value>)",
        "confidence-high-bg": "rgb(var(--confidence-high-bg) / <alpha-value>)",
        "confidence-high-fg": "rgb(var(--confidence-high-fg) / <alpha-value>)",
        "confidence-medium-bg": "rgb(var(--confidence-medium-bg) / <alpha-value>)",
        "confidence-medium-fg": "rgb(var(--confidence-medium-fg) / <alpha-value>)",
        "confidence-low-bg": "rgb(var(--confidence-low-bg) / <alpha-value>)",
        "confidence-low-fg": "rgb(var(--confidence-low-fg) / <alpha-value>)",
        "alert-info-bg": "rgb(var(--alert-info-bg) / <alpha-value>)",
        "alert-info-fg": "rgb(var(--alert-info-fg) / <alpha-value>)",
        "alert-success-bg": "rgb(var(--alert-success-bg) / <alpha-value>)",
        "alert-success-fg": "rgb(var(--alert-success-fg) / <alpha-value>)",
        "alert-warning-bg": "rgb(var(--alert-warning-bg) / <alpha-value>)",
        "alert-warning-fg": "rgb(var(--alert-warning-fg) / <alpha-value>)",
        "alert-error-bg": "rgb(var(--alert-error-bg) / <alpha-value>)",
        "alert-error-fg": "rgb(var(--alert-error-fg) / <alpha-value>)",
      },
      spacing: {
        header: "4.25rem",
        sidebar: "17rem",
        gutter: "1.5rem",
      },
      borderRadius: {
        control: "0.7rem",
        card: "1.15rem",
      },
      boxShadow: {
        card: "0 1px 0 rgb(16 32 48 / 0.05), 0 18px 40px rgb(16 32 48 / 0.06)",
        pop: "0 24px 64px rgb(16 32 48 / 0.22)",
      },
      fontFamily: {
        sans: ["Source Sans 3", "Segoe UI", "sans-serif"],
        display: ["Fraunces", "Georgia", "serif"],
        mono: ["IBM Plex Mono", "Consolas", "monospace"],
      },
      fontSize: {
        display: ["3.15rem", { lineHeight: "1.05", letterSpacing: "-0.03em", fontWeight: "560" }],
        title: ["1.85rem", { lineHeight: "1.15", letterSpacing: "-0.02em" }],
      },
    },
  },
  plugins: [],
} satisfies Config;

export default config;
