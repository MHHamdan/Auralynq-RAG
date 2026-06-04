import Link from "next/link";
import { ThemeToggle } from "@/components/ThemeToggle";

const REPO = "https://github.com/MHHamdan/Auralynq";

export function Nav() {
  return (
    <header className="sticky top-0 z-50 border-b border-edge bg-ink/80 backdrop-blur-xl">
      <nav className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 md:px-6">
        <Link href="/" className="flex items-center gap-2 text-lg font-bold tracking-tight text-fg">
          <span aria-hidden>🎙️</span>
          <span>
            <span className="text-brand">Aura</span>
            <span className="text-brand2">lynq</span>
          </span>
        </Link>

        <div className="hidden items-center gap-7 text-sm font-medium text-fg2 md:flex">
          <a href="#features" className="transition hover:text-fg">
            Features
          </a>
          <a href="#how" className="transition hover:text-fg">
            How it works
          </a>
          <a href="#why" className="transition hover:text-fg">
            Why
          </a>
          <a href="#stack" className="transition hover:text-fg">
            Architecture
          </a>
          <a href={REPO} target="_blank" rel="noopener noreferrer" className="transition hover:text-fg">
            GitHub
          </a>
        </div>

        <div className="flex items-center gap-2">
          <ThemeToggle compact />
          <Link href="/chat" className="btn-cta text-sm">
            Launch app →
          </Link>
        </div>
      </nav>
    </header>
  );
}
