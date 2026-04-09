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
        sans: ['"SF Pro Display"', '"Helvetica Neue"', '"Segoe UI"', "sans-serif"],
      },
      boxShadow: {
        panel: "0 18px 42px rgba(20, 35, 60, 0.08)",
      },
    },
  },
  plugins: [],
};
