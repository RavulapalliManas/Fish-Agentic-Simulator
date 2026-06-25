/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        accent: {
          50: "#eef6ff",
          100: "#dcecff",
          500: "#2d7dff",
          600: "#1f68db",
          700: "#164ea8",
        },
      },
      fontFamily: {
        sans: ['"Inter Variable"', "system-ui", '"Segoe UI"', "sans-serif"],
        mono: ['"JetBrains Mono Variable"', "ui-monospace", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};
