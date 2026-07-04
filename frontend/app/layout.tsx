import type { Metadata } from "next";
import { Noto_Sans_TC } from "next/font/google";

import "./globals.css";

const notoSans = Noto_Sans_TC({
  variable: "--font-noto-sans-tc",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "台股起漲雷達",
  description: "透明、可回測的台股盤後選股儀表板",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-Hant">
      <body className={notoSans.variable}>{children}</body>
    </html>
  );
}

