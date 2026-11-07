import { useState } from 'react';

export default function App() {
  const [expanded, setExpanded] = useState(false);
  const [reviewed, setReviewed] = useState(false);
  return (
    <div className="min-h-screen bg-[#f6f7f9] text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-5 py-5 sm:px-8">
          <div className="flex items-center gap-3"><span aria-hidden="true" className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-700 text-sm font-semibold text-white">F</span><span className="font-semibold tracking-tight">Fieldwork</span><span className="hidden text-sm text-slate-500 sm:block">/ Document review</span></div>
          <span className="rounded-full border border-slate-200 px-3 py-1 text-xs font-medium text-slate-600">Local demo</span>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-5 py-10 sm:px-8 sm:py-14">
        <div className="mb-9 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
          <div><p className="mb-3 text-xs font-semibold uppercase tracking-[0.16em] text-indigo-700">Project brief · 01</p><h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">A clearer way forward.</h1><p className="mt-3 max-w-xl text-base leading-7 text-slate-600">Review the proposal, check the open question, and mark it ready for the next conversation.</p></div>
          <button onClick={() => setReviewed(!reviewed)} className="min-h-11 shrink-0 rounded-lg bg-indigo-700 px-5 py-3 text-sm font-medium text-white transition-colors hover:bg-indigo-800">{reviewed ? 'Reopen review' : 'Mark as reviewed'}</button>
        </div>
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_18rem]">
          <article className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-6 py-5"><h2 className="font-semibold">Community garden proposal</h2><span className={'rounded-full px-3 py-1 text-xs font-medium ' + (reviewed ? 'bg-emerald-50 text-emerald-800' : 'bg-amber-50 text-amber-900')}>{reviewed ? 'Reviewed' : 'Awaiting review'}</span></div>
            <div className="space-y-7 px-6 py-7 sm:px-8">
              <section><h3 className="text-sm font-semibold">The opportunity</h3><p className="mt-2 max-w-prose text-base leading-7 text-slate-600">Turn an unused corner of the neighborhood into a welcoming place to grow food, share skills, and meet each other.</p></section>
              <section><h3 className="text-sm font-semibold">A small, practical start</h3><p className="mt-2 max-w-prose text-base leading-7 text-slate-600">Begin with four raised beds and a shared tool cabinet. A weekly volunteer rota will keep care predictable without asking too much of any one person.</p></section>
              <section className="rounded-lg border border-slate-200 bg-slate-50"><button aria-expanded={expanded} aria-controls="open-question" onClick={() => setExpanded(!expanded)} className="flex min-h-12 w-full items-center justify-between gap-4 px-4 py-3 text-left text-sm font-medium"><span>One question before we begin</span><span aria-hidden="true" className="text-lg">{expanded ? '−' : '+'}</span></button>{expanded && <p id="open-question" className="border-t border-slate-200 px-4 py-4 text-sm leading-6 text-slate-600">Who will hold the spare cabinet key? Add an owner before the first planting day.</p>}</section>
            </div>
          </article>
          <aside className="space-y-5"><section className="rounded-xl border border-slate-200 bg-white p-6"><h2 className="text-sm font-semibold">Review details</h2><dl className="mt-5 space-y-4 text-sm"><div className="flex justify-between gap-4"><dt className="text-slate-600">Prepared by</dt><dd className="font-medium">Maya Chen</dd></div><div className="flex justify-between gap-4"><dt className="text-slate-600">Version</dt><dd className="font-medium">Draft 01</dd></div><div className="flex justify-between gap-4"><dt className="text-slate-600">Read time</dt><dd className="font-medium">2 minutes</dd></div></dl></section><p className="px-1 text-sm leading-6 text-slate-600">This sample stays in your browser. Reviewing changes its local status; no document is sent or published.</p></aside>
        </div>
      </main>
    </div>
  );
}
