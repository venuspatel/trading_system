import { createContext, useContext, useState, useEffect } from "react";

const THEMES = {
  "Pure Black": {
    bg0: "#000000", bg1: "#0a0a0a", bg2: "#0f0f0f", bg3: "#111111",
    border: "#252525", borderSub: "#1e1e1e",
    textPrimary: "#e0e0e0", textSecondary: "#999999", textMuted: "#666666",
    accent: "#4d9cf8", profit: "#22c55e", loss: "#ef4444",
    warning: "#f59e0b", signal: "#a78bfa",
    cardBg: "#0a0a0a", navActive: "#0d1f3c",
  },
  "Charcoal": {
    bg0: "#0d0d0d", bg1: "#141414", bg2: "#1a1a1a", bg3: "#202020",
    border: "#2e2e2e", borderSub: "#252525",
    textPrimary: "#ececec", textSecondary: "#aaaaaa", textMuted: "#777777",
    accent: "#4d9cf8", profit: "#22c55e", loss: "#ef4444",
    warning: "#f59e0b", signal: "#a78bfa",
    cardBg: "#141414", navActive: "#0d1f3c",
  },
  "Midnight Blue": {
    bg0: "#060b14", bg1: "#0a1120", bg2: "#0d1628", bg3: "#111d33",
    border: "#1e2d45", borderSub: "#182338",
    textPrimary: "#dde8f5", textSecondary: "#8aa4c4", textMuted: "#5a7a9a",
    accent: "#4d9cf8", profit: "#22c55e", loss: "#ef4444",
    warning: "#f59e0b", signal: "#a78bfa",
    cardBg: "#0a1120", navActive: "#0d2a50",
  },
  "Midnight Teal": {
    bg0: "#020f0c", bg1: "#071512", bg2: "#0a1c18", bg3: "#0e2420",
    border: "#1a3330", borderSub: "#142820",
    textPrimary: "#d4f0ec", textSecondary: "#6ab8ae", textMuted: "#3a7a72",
    accent: "#2dd4bf", profit: "#22c55e", loss: "#ef4444",
    warning: "#f59e0b", signal: "#a78bfa",
    cardBg: "#071512", navActive: "#0a2e28",
  },
  "Slate & Gold": {
    bg0: "#08080f", bg1: "#10101e", bg2: "#14142a", bg3: "#1a1a32",
    border: "#28284a", borderSub: "#20203a",
    textPrimary: "#f0ecff", textSecondary: "#9090c0", textMuted: "#606090",
    accent: "#f59e0b", profit: "#22c55e", loss: "#ef4444",
    warning: "#f59e0b", signal: "#a78bfa",
    cardBg: "#10101e", navActive: "#20204a",
  },
  "Deep Forest": {
    bg0: "#060c08", bg1: "#0c1410", bg2: "#101a14", bg3: "#15221a",
    border: "#1e3028", borderSub: "#182618",
    textPrimary: "#d8f0e0", textSecondary: "#7aaa88", textMuted: "#4a7a58",
    accent: "#4ade80", profit: "#4ade80", loss: "#ef4444",
    warning: "#f59e0b", signal: "#a78bfa",
    cardBg: "#0c1410", navActive: "#0a2a18",
  },
};

const ACCENT_COLORS = {
  "Blue":   "#4d9cf8",
  "Teal":   "#2dd4bf",
  "Purple": "#a78bfa",
  "Gold":   "#f59e0b",
  "White":  "#e0e0e0",
  "Green":  "#4ade80",
};

const FONT_SIZES = { "Small": 11, "Default": 13, "Large": 15 };
const NEWS_COLOR_SCHEMES = ["Red → Green", "Blue → Amber", "Purple → Teal", "Monochrome"];

const DEFAULT_THEME = "Pure Black";

const ThemeContext = createContext(null);

export function ThemeProvider({ children }) {
  const [themeName,  setThemeName]  = useState(() => localStorage.getItem("ta_theme")  || DEFAULT_THEME);
  const [accentName, setAccentName] = useState(() => localStorage.getItem("ta_accent") || "Blue");
  const [fontSize,   setFontSize]   = useState(() => localStorage.getItem("ta_font")   || "Default");
  const [compact,    setCompact]    = useState(() => localStorage.getItem("ta_compact") === "true");
  const [newsColorScheme, setNewsColorScheme] = useState(() => localStorage.getItem("ta_news_scheme") || "Red → Green");

  const theme = { ...THEMES[themeName] || THEMES[DEFAULT_THEME], accent: ACCENT_COLORS[accentName] || ACCENT_COLORS["Blue"] };

  useEffect(() => { localStorage.setItem("ta_theme",   themeName);  }, [themeName]);
  useEffect(() => { localStorage.setItem("ta_accent",  accentName); }, [accentName]);
  useEffect(() => { localStorage.setItem("ta_font",    fontSize);   }, [fontSize]);
  useEffect(() => { localStorage.setItem("ta_compact", compact);    }, [compact]);
  useEffect(() => { localStorage.setItem("ta_news_scheme", newsColorScheme); }, [newsColorScheme]);

  return (
    <ThemeContext.Provider value={{ theme, themeName, setThemeName, accentName, setAccentName, fontSize, setFontSize, compact, setCompact, THEMES, ACCENT_COLORS, FONT_SIZES }}>
      {children}
    </ThemeContext.Provider>
  );
}

export const useTheme = () => useContext(ThemeContext);
export { THEMES, ACCENT_COLORS, FONT_SIZES, NEWS_COLOR_SCHEMES };
