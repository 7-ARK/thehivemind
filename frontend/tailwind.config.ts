import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{js,ts,jsx,tsx}", "./components/**/*.{js,ts,jsx,tsx}", "./lib/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        hive: {
          bg: "#171717",
          shell: "#1c1c1b",
          panel: "#232321",
          panelSoft: "#2b2a27",
          card: "#302f2b",
          border: "#44413b",
          text: "#f3efe7",
          muted: "#a9a197",
          faint: "#746d63",
          accent: "#c4934d",
          amber: "#d5a253",
          green: "#8fb996",
          cyan: "#86b8b2",
          warning: "#b98143"
        }
      },
      boxShadow: {
        panel: "0 18px 60px rgba(0, 0, 0, 0.22)",
        inset: "inset 0 1px 0 rgba(255, 255, 255, 0.035)"
      }
    }
  },
  plugins: []
};

export default config;
