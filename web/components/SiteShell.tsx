import type { ReactNode } from "react";
import { Disclaimer } from "./Disclaimer";

/** Header, content, and the disclaimer footer. Every route renders inside this, so no page can omit it. */
export function SiteShell({ children }: { children: ReactNode }) {
  return (
    <div className="shell">
      <header className="site-header">
        <a href="/" className="brand">
          BankManager
        </a>
        <span className="tagline">AI equity research, checked</span>
        <nav>
          <a href="/">Analyze</a>
          <a href="/demo">ACME demo</a>
        </nav>
      </header>
      <main>{children}</main>
      <footer className="site-footer">
        <Disclaimer />
      </footer>
    </div>
  );
}
