import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        cockpit: {
          bg: "#080b10",
          panel: "#10151d",
          panel2: "#151c26",
          line: "#263241",
          text: "#e5edf6",
          muted: "#8fa0b3"
        }
      },
      boxShadow: {
        panel: "0 18px 60px rgba(0, 0, 0, 0.28)"
      }
    }
  },
  plugins: []
};

export default config;
