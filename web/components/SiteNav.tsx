"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

const LINKS = [
  { href: "/", label: "Analyze" },
  { href: "/how-it-works", label: "How it works" },
  { href: "/data", label: "Live SEC data" },
  { href: "/demo", label: "Full AI report example" },
];

type Theme = "system" | "light" | "dark";
const NEXT: Record<Theme, Theme> = { system: "light", light: "dark", dark: "system" };
const ICON: Record<Theme, string> = { system: "◐ Auto", light: "☀ Light", dark: "☾ Dark" };

/** Nav pills with the current page marked, plus a system / light / dark toggle (the choice is remembered when storage allows). */
export function SiteNav() {
  const path = usePathname();
  const [theme, setTheme] = useState<Theme>("system");

  useEffect(() => {
    try {
      const saved = localStorage.getItem("bm-theme");
      if (saved === "light" || saved === "dark") setTheme(saved);
    } catch {
      /* storage blocked: stay on system */
    }
  }, []);

  function cycle() {
    const next = NEXT[theme];
    setTheme(next);
    if (next === "system") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = next;
    try {
      if (next === "system") localStorage.removeItem("bm-theme");
      else localStorage.setItem("bm-theme", next);
    } catch {
      /* not persisted; still applied for this visit */
    }
  }

  return (
    <>
      <nav aria-label="Main">
        {LINKS.map((l) => (
          <Link key={l.href} href={l.href} aria-current={path === l.href ? "page" : undefined}>
            {l.label}
          </Link>
        ))}
      </nav>
      <button type="button" className="theme-toggle" onClick={cycle} aria-label={`Theme: ${theme}. Click to change.`}>
        {ICON[theme]}
      </button>
    </>
  );
}
