// Shared Tailwind CDN config for the Ada Desk site.
// Dynamic theme variable integration for Light & Dark mode.
tailwind.config = {
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        "on-secondary-fixed": "#2a1700",
        "tertiary-fixed": "#ffdad7",
        "on-primary-container": "#00422b",
        "surface-bright": "var(--color-surface-container-high)",
        "inverse-on-surface": "#31302f",
        "on-surface-variant": "var(--color-on-surface-variant)",
        "on-secondary-fixed-variant": "#653e00",
        "on-tertiary-fixed-variant": "#930013",
        "surface-container-lowest": "var(--color-surface-container-lowest)",
        "ai-glow": "var(--pulse-border-glow)",
        "on-error-container": "#ffdad6",
        "secondary-fixed": "#ffddb8",
        "surface": "var(--color-surface)",
        "tertiary-fixed-dim": "#ffb3ad",
        "outline": "#86948a",
        "outline-variant": "var(--color-surface-container-high)",
        "surface-container": "var(--color-surface-container)",
        "on-primary-fixed-variant": "#005236",
        "primary-fixed": "var(--color-primary-fixed)",
        "tertiary-container": "#ff7a73",
        "secondary": "var(--color-secondary)",
        "inverse-primary": "#006c49",
        "surface-container-low": "var(--color-surface-container-low)",
        "inverse-surface": "var(--color-on-surface)",
        "on-tertiary": "#68000a",
        "on-background": "var(--color-on-surface)",
        "tertiary": "var(--color-tertiary)",
        "on-primary": "var(--color-on-primary)",
        "secondary-container": "#ee9800",
        "surface-elevated": "var(--color-surface-elevated)",
        "background": "var(--bg-body)",
        "on-tertiary-fixed": "#410004",
        "surface-dim": "var(--color-surface)",
        "surface-container-highest": "var(--color-surface-container-highest)",
        "on-secondary": "#472a00",
        "on-surface": "var(--color-on-surface)",
        "surface-variant": "var(--color-surface-container-high)",
        "error": "var(--color-error)",
        "on-tertiary-container": "#79000e",
        "on-primary-fixed": "#002113",
        "on-error": "#690005",
        "surface-container-high": "var(--color-surface-container-high)",
        "primary": "var(--color-primary)",
        "secondary-fixed-dim": "#ffb95f",
        "primary-container": "var(--color-primary-container)",
        "surface-deep": "var(--bg-body)",
        "on-secondary-container": "#5b3800",
        "error-container": "#93000a",
        "primary-fixed-dim": "var(--color-primary)",
        "surface-tint": "var(--color-primary)",
        "glass-stroke": "var(--color-glass-stroke)"
      },
      borderRadius: {
        DEFAULT: "0.125rem",
        lg: "0.25rem",
        xl: "0.5rem",
        full: "0.75rem"
      },
      spacing: {
        "margin-mobile": "16px",
        "max-width": "1440px",
        "margin-desktop": "64px",
        "unit": "4px",
        "gutter": "24px"
      },
      fontFamily: {
        "body-md": ["DM Sans", "sans-serif"],
        "label-caps": ["JetBrains Mono", "monospace"],
        "code-sm": ["JetBrains Mono", "monospace"],
        "headline-lg": ["Space Grotesk", "sans-serif"],
        "headline-xl": ["Space Grotesk", "sans-serif"],
        "body-sm": ["DM Sans", "sans-serif"],
        "headline-lg-mobile": ["Space Grotesk", "sans-serif"]
      },
      fontSize: {
        "body-md": ["16px", { lineHeight: "24px", fontWeight: "400" }],
        "label-caps": ["12px", { lineHeight: "16px", letterSpacing: "0.08em", fontWeight: "600" }],
        "code-sm": ["13px", { lineHeight: "18px", fontWeight: "400" }],
        "headline-lg": ["32px", { lineHeight: "40px", letterSpacing: "-0.01em", fontWeight: "600" }],
        "headline-xl": ["48px", { lineHeight: "56px", letterSpacing: "-0.02em", fontWeight: "700" }],
        "body-sm": ["14px", { lineHeight: "20px", fontWeight: "400" }],
        "headline-lg-mobile": ["24px", { lineHeight: "32px", fontWeight: "600" }]
      }
    }
  }
};
