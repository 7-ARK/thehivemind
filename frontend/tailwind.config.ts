import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{js,ts,jsx,tsx}", "./components/**/*.{js,ts,jsx,tsx}", "./lib/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        hive: {
          bg: "#080b12",
          panel: "#101620",
          panelSoft: "#151d2a",
          border: "#263244",
          text: "#e5edf8",
          muted: "#94a3b8",
          accent: "#f0b429",
          teal: "#35c2a1"
        }
      },
      boxShadow: {
        panel: "0 18px 70px rgba(0, 0, 0, 0.28)"
      }
    }
  },
  plugins: []
};

export default config;

