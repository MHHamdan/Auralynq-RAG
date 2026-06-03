const STEPS = [
  {
    n: "01",
    title: "Ingest",
    body: "Drop in PDFs, docs, web pages or audio. Auralynq chunks, embeds and indexes them into a hybrid vector store and a relational knowledge graph.",
  },
  {
    n: "02",
    title: "Ask",
    body: "Type or speak your question. An adaptive router decides between fast vector search and deep PathRAG graph traversal based on what you asked.",
  },
  {
    n: "03",
    title: "Answer",
    body: "Get a streamed, grounded answer with inline citations — plus the reasoning trace and evidence paths, so you can see exactly how it got there.",
  },
];

export function HowItWorks() {
  return (
    <section id="how" className="relative mx-auto max-w-6xl px-4 py-20 md:px-6">
      <div className="mb-12 max-w-2xl">
        <p className="mb-2 text-sm font-semibold uppercase tracking-widest text-brand2">How it works</p>
        <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">From documents to cited answers in three steps</h2>
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        {STEPS.map((s, i) => (
          <div key={s.n} className="relative glass p-6">
            <div className="mb-3 text-3xl font-bold gradient-text">{s.n}</div>
            <h3 className="mb-2 text-lg font-semibold text-white">{s.title}</h3>
            <p className="text-sm leading-relaxed text-slate-300">{s.body}</p>
            {i < STEPS.length - 1 && (
              <span className="absolute -right-2 top-1/2 hidden -translate-y-1/2 text-2xl text-edge md:block">
                →
              </span>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
