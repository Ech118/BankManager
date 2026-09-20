import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import type { ReactNode } from "react";
import { SiteShell } from "@/components/SiteShell";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains", display: "swap" });

export const metadata: Metadata = {
  title: "BankManager: AI equity research",
  description: "Enter a ticker. Get a checked research report and a verdict on whether it beats the S&P 500. Educational only.",
};

/** Applies a saved theme before first paint, so a light/dark choice never flashes. Static string, no user input. */
const THEME_INIT = `try{var t=localStorage.getItem("bm-theme");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${mono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT }} />
      </head>
      {/* suppressHydrationWarning: extensions such as Grammarly add attributes to body before React loads */}
      <body suppressHydrationWarning>
        <SiteShell>{children}</SiteShell>
      </body>
    </html>
  );
}
