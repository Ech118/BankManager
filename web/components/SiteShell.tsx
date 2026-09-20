import Link from "next/link";
import type { ReactNode } from "react";
import { Disclaimer } from "./Disclaimer";

/** Header, content, and the disclaimer footer. Every route renders inside this, so no page can omit it. */
export function SiteShell({ children }: { children: ReactNode }) {
  return (
    <div className="shell">
      <header className="site-header">
        <Link href="/" className="brand">
          BankManager
        </Link>
        <span className="tagline">AI equity research, checked</span>
        <nav>
          <Link href="/">Analyze</Link>
          <Link href="/data">Live SEC data</Link>
          <Link href="/demo">Full AI report example</Link>
        </nav>
      </header>
      <main>{children}</main>
      <footer className="site-footer">
        <Disclaimer />
      </footer>
    </div>
  );
}
