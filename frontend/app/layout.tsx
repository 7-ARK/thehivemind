import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TheHiveMind",
  description: "Multi-agent AI operating system for planning, delegation, memory, and execution."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

