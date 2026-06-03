import Link from "next/link";

const REPO = "https://github.com/MHHamdan/Auralynq";

export function Nav() {
  return (
    <header className="sticky top-0 z-50 border-b border-white/5 bg-ink/70 backdrop-blur-xl">
      <nav className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 md:px-6">
        <Link href="/" className="flex items-center gap-2 text-lg font-bold tracking-tight">
          <span aria-hidden>🎙️</span>
          <span>
            <span className="text-brand">Aura</span>
            <span className="text-brand2">lynq</span>
          </span>
        </Link>

        <div className="hidden items-center gap-7 text-sm text-slate-200 md:flex">
          <a href="#features" className="transition hover:text-white">
            Features
          </a>
          <a href="#how" className="transition hover:text-white">
            How it works
          </a>
          <a href="#stack" className="transition hover:text-white">
            Architecture
          </a>
          <a href={REPO} target="_blank" rel="noopener noreferrer" className="transition hover:text-white">
            GitHub
          </a>
        </div>

        <Link href="/chat" className="btn-cta text-sm">
          Launch app →
        </Link>
      </nav>
    </header>
  );
}
