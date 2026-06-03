import type { Metadata } from "next";
import "highlight.js/styles/github-dark.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "Auralynq — Talk to Your Data",
  description:
    "Local-first, agentic, voice-enabled RAG with PathRAG graph retrieval. Grounded, cited answers.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
