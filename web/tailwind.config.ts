import type { Config } from "tailwindcss";
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#070b16",
        panel: "#0e1424",
        edge: "#1f2a44",
        brand: "#5eead4", // teal
        brand2: "#818cf8", // indigo
        accent: "#c084fc", // violet
        accent2: "#f472b6", // pink
      },
      fontFamily: {
        sans: ["var(--font-inter)", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(16px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        float: {
          "0%,100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-12px)" },
        },
        "orb-drift": {
          "0%,100%": { transform: "translate(0,0) scale(1)" },
          "50%": { transform: "translate(20px,-20px) scale(1.08)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "200% 0" },
          "100%": { backgroundPosition: "-200% 0" },
        },
        "pulse-soft": {
          "0%,100%": { opacity: "0.6" },
          "50%": { opacity: "1" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.6s ease-out both",
        float: "float 6s ease-in-out infinite",
        "orb-drift": "orb-drift 14s ease-in-out infinite",
        shimmer: "shimmer 6s linear infinite",
        "pulse-soft": "pulse-soft 2.4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
export default config;
