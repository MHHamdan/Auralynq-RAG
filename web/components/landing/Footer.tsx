import Link from "next/link";

const REPO = "https://github.com/MHHamdan/Auralynq";

export function Footer() {
  return (
    <footer className="border-t border-white/5">
      <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-4 py-8 text-sm text-slate-400 md:flex-row md:px-6">
        <div className="flex items-center gap-2 font-semibold">
          <span aria-hidden>🎙️</span>
          <span>
            <span className="text-brand">Aura</span>
            <span className="text-brand2">lynq</span>
          </span>
          <span className="ml-2 font-normal text-slate-500">Talk to Your Data</span>
        </div>
        <div className="flex items-center gap-6">
          <Link href="/chat" className="transition hover:text-white">
            Launch app
          </Link>
          <a href="#features" className="transition hover:text-white">
            Features
          </a>
          <a href={REPO} target="_blank" rel="noopener noreferrer" className="transition hover:text-white">
            GitHub
          </a>
        </div>
        <div className="text-xs text-slate-500">Local-first · $0 default · Open source</div>
      </div>
    </footer>
  );
}
