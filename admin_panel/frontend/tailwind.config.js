/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        border: "hsl(215 20% 20%)",
        background: "hsl(222 32% 8%)",
        card: "hsl(222 28% 11%)",
        muted: "hsl(217 20% 16%)",
        "muted-foreground": "hsl(215 16% 60%)",
        foreground: "hsl(210 40% 96%)",
        primary: "hsl(199 89% 52%)",
        "primary-foreground": "hsl(222 47% 8%)",
        success: "hsl(142 71% 45%)",
        danger: "hsl(0 72% 55%)",
        warning: "hsl(38 92% 55%)",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
