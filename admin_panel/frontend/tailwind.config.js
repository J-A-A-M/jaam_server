/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        border: "rgba(255,255,255,0.07)",
        background: "#07080D",
        card: "#0B0D14",
        muted: "#10131C",
        "muted-foreground": "#48526A",
        foreground: "#C4CFDF",
        primary: "#F59E0B",
        "primary-foreground": "#07080D",
        accent: "#22D3EE",
        "accent-foreground": "#07080D",
        success: "#10B981",
        danger: "#EF4444",
        warning: "#F59E0B",
      },
      fontFamily: {
        sans: ["Syne", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      boxShadow: {
        glow: "0 0 20px rgba(245,158,11,0.18)",
        "glow-sm": "0 0 8px rgba(245,158,11,0.10)",
        "glow-success": "0 0 10px rgba(16,185,129,0.22)",
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-in": "fadeIn 0.4s ease forwards",
      },
      keyframes: {
        fadeIn: {
          from: { opacity: "0", transform: "translateY(5px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
};
