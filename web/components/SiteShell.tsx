import Link from "next/link";
import type { ReactNode } from "react";
import { Disclaimer } from "./Disclaimer";
import { SiteNav } from "./SiteNav";

/** Header, content, and the disclaimer footer. Every route renders inside this, so no page can omit it. */
export function SiteShell({ children }: { children: ReactNode }) {
  return (
    <div className="shell">
      <header className="site-header">
        <Link href="/" className="brand">
          <span className="brand-mark" aria-hidden="true">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M2 12l4-4 3 3 5-6" />
            </svg>
          </span>
          BankManager
        </Link>
        <span className="tagline">AI equity research, checked</span>
        <SiteNav />
      </header>
      <main>{children}</main>
      <footer className="site-footer">
        <Disclaimer />
      </footer>
    </div>
  );
}
