import type { Metadata } from "next";
import { Hanken_Grotesk, Geist_Mono } from "next/font/google";
import "@xyflow/react/dist/style.css";
import "./globals.css";
import { Shell } from "@/components/shell";

const hanken = Hanken_Grotesk({ variable: "--font-hanken", subsets: ["latin"], weight: ["400", "500", "600"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Keepline",
  description: "Glean finds what your company knows. Keepline shows what it's about to forget, and saves it.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${hanken.variable} ${geistMono.variable} antialiased`}>
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
