"use client";
import { useRef, type ComponentPropsWithoutRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";

// Close an unterminated ``` fence so a partial markdown stream never renders a
// half-open code block that swallows the rest of the message (streaming pattern
// borrowed from production chat UIs: show text live, keep code blocks coherent).
function closeOpenFence(md: string): string {
  const fences = (md.match(/```/g) || []).length;
  return fences % 2 === 1 ? `${md}\n\`\`\`` : md;
}

function PreBlock({ children }: ComponentPropsWithoutRef<"pre">) {
  const ref = useRef<HTMLPreElement>(null);
  return (
    <div className="group/code relative">
      <button
        type="button"
        aria-label="Copy code"
        onClick={() => navigator.clipboard?.writeText(ref.current?.innerText ?? "")}
        className="absolute right-2 top-2 rounded-md border border-edge bg-panel/80 px-2 py-0.5 text-xs text-slate-400 opacity-0 transition hover:text-brand group-hover/code:opacity-100"
      >
        Copy
      </button>
      <pre ref={ref}>{children}</pre>
    </div>
  );
}

export function Markdown({ text, streaming = false }: { text: string; streaming?: boolean }) {
  const src = streaming ? closeOpenFence(text) : text;
  return (
    <div className="prose-auralynq">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypeHighlight, { detect: true, ignoreMissing: true }]]}
        components={{
          a: (props) => <a {...props} target="_blank" rel="noopener noreferrer" />,
          pre: PreBlock,
        }}
      >
        {src}
      </ReactMarkdown>
    </div>
  );
}
