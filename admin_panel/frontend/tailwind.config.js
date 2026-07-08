/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background:          "rgb(var(--bg) / <alpha-value>)",
        card:                "rgb(var(--card) / <alpha-value>)",
        muted:               "rgb(var(--muted) / <alpha-value>)",
        "muted-foreground":  "rgb(var(--muted-fg) / <alpha-value>)",
        foreground:          "rgb(var(--fg) / <alpha-value>)",
        border:              "rgb(var(--border) / <alpha-value>)",
        primary:             "rgb(var(--primary) / <alpha-value>)",
        "primary-foreground":"rgb(var(--primary-fg) / <alpha-value>)",
        success:             "rgb(var(--success) / <alpha-value>)",
        danger:              "rgb(var(--danger) / <alpha-value>)",
        warning:             "rgb(var(--primary) / <alpha-value>)",
        accent:              "#22D3EE",
        "accent-foreground": "rgb(var(--bg) / <alpha-value>)",
        sidebar:             "rgb(var(--sidebar) / <alpha-value>)",
      },
      fontFamily: {
        sans: ["Syne", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      boxShadow: {
        glow:         "0 0 20px rgb(var(--primary) / 0.18)",
        "glow-sm":    "0 0 8px rgb(var(--primary) / 0.12)",
        "glow-success": "0 0 10px rgba(16,185,129,0.22)",
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-in":    "fadeIn 0.4s ease forwards",
      },
      keyframes: {
        fadeIn: {
          from: { opacity: "0", transform: "translateY(5px)" },
          to:   { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
};
