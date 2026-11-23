import { useEffect, useState } from "react";
import styles from "../ui/controls.module.css";

type Theme = "light" | "dark";

function initial(): Theme {
  try {
    const saved = localStorage.getItem("sentinel-theme");
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    /* storage can be unavailable */
  }
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(initial);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("sentinel-theme", theme);
    } catch {
      /* ignore */
    }
  }, [theme]);
  return (
    <button type="button" className={styles.pill} aria-pressed={theme === "dark"} onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
      {theme === "dark" ? "Light theme" : "Dark theme"}
    </button>
  );
}
