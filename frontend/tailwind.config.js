/* tailwind.config.js
   Loaded via <script src="tailwind.config.js"> on pages that use Tailwind utilities.
   chat.html and dashboard.html reference this.
   clinical.css owns all design tokens as CSS custom properties. */

tailwind.config = {
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        "surface-variant": "#d3e4fe",
        "surface-bright": "#f8f9ff",
        "surface-dim": "#cbdbf5",
        surface: "#f8f9ff",
        "surface-container-lowest": "#ffffff",
        "surface-container-low": "#eff4ff",
        "surface-container": "#e5eeff",
        "surface-container-high": "#dce9ff",
        "surface-container-highest": "#d3e4fe",
        primary: "#004ac6",
        "primary-container": "#2563eb",
        "primary-fixed": "#dbe1ff",
        "primary-fixed-dim": "#b4c5ff",
        "inverse-primary": "#b4c5ff",
        "surface-tint": "#0053db",
        secondary: "#006a61",
        "secondary-container": "#86f2e4",
        "on-secondary-container": "#006f66",
        tertiary: "#ac0031",
        "tertiary-container": "#d71142",
        "on-tertiary-container": "#ffecec",
        error: "#ba1a1a",
        "error-container": "#ffdad6",
        "on-error": "#ffffff",
        "on-surface": "#0b1c30",
        "on-surface-variant": "#434655",
        "on-primary": "#ffffff",
        "on-secondary": "#ffffff",
        "on-tertiary": "#ffffff",
        "on-background": "#0b1c30",
        "on-primary-container": "#eeefff",
        outline: "#737686",
        "outline-variant": "#c3c6d7",
        "inverse-surface": "#213145",
        "inverse-on-surface": "#eaf1ff",
        background: "#f8f9ff",
      },
      fontFamily: {
        headline: ["Manrope", "sans-serif"],
        body: ["Inter", "sans-serif"],
        label: ["Inter", "sans-serif"],
      },
      borderRadius: {
        DEFAULT: "0.25rem",
        lg: "1rem",
        xl: "1.5rem",
        full: "9999px",
      },
    },
  },
};
