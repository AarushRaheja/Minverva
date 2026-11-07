import { useState } from 'react';

type Preferences = { email: boolean; push: boolean; digest: string };
const defaults: Preferences = { email: true, push: false, digest: 'Daily' };

function Switch({ label, description, checked, onChange, testId }: {
  label: string; description: string; checked: boolean; onChange: () => void; testId: string;
}) {
  return <div className="flex items-center justify-between gap-5 py-6">
    <div><p className="text-sm font-semibold text-slate-900">{label}</p><p className="mt-1 max-w-md text-sm leading-6 text-slate-600">{description}</p></div>
    <button type="button" role="switch" aria-checked={checked} aria-label={label} data-testid={testId} onClick={onChange}
      className="flex min-h-11 min-w-12 shrink-0 items-center justify-center rounded-lg">
      <span aria-hidden="true" className={'flex h-6 w-11 items-center rounded-full p-1 transition-colors ' + (checked ? 'justify-end bg-indigo-700' : 'justify-start bg-slate-500')}><span className="h-4 w-4 rounded-full bg-white shadow-sm" /></span>
    </button>
  </div>;
}

export default function App() {
  const [draft, setDraft] = useState<Preferences>(defaults);
  const [saved, setSaved] = useState<Preferences>(defaults);
  const [message, setMessage] = useState('');
  const dirty = JSON.stringify(draft) !== JSON.stringify(saved);
  function change(next: Preferences) { setDraft(next); setMessage(''); }
  function save() { setSaved({ ...draft }); setMessage('Preferences saved for this preview.'); }
  function reset() { change({ ...defaults }); }

  return <div className="min-h-screen bg-[#f7f8fa] text-slate-900">
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-5 py-5 sm:px-8">
        <div className="flex items-center gap-3"><span aria-hidden="true" className="grid h-8 w-8 place-items-center rounded-lg bg-slate-900 text-xs font-semibold text-white">N</span><span className="text-sm font-semibold">Northstar</span><span className="hidden text-sm text-slate-500 sm:inline">/ Personal settings</span></div>
        <span className="rounded-md border border-slate-200 px-2.5 py-1 text-xs text-slate-600">Interactive preview</span>
      </div>
    </header>
    <main className="mx-auto max-w-6xl px-5 py-10 sm:px-8 sm:py-14">
      <div className="mb-9 max-w-2xl"><p className="mb-3 text-xs font-semibold uppercase tracking-[0.16em] text-indigo-700">Notifications</p><h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Make room for focus.</h1><p className="mt-3 text-base leading-7 text-slate-600">Choose how you hear from your workspace. Keep the useful updates, and leave the rest for later.</p></div>
      <div className="grid items-start gap-7 lg:grid-cols-[minmax(0,1fr)_17rem]">
        <form onSubmit={event => { event.preventDefault(); save(); }} className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 px-6 py-5"><h2 className="text-base font-semibold">Delivery preferences</h2><p className="mt-1 text-sm leading-6 text-slate-600">Changes apply when you save this preview.</p></div>
          <div className="divide-y divide-slate-200 px-6 sm:px-7">
            <Switch label="Email updates" description="A summary of activity that needs your attention." checked={draft.email} onChange={() => change({ ...draft, email: !draft.email })} testId="email-setting" />
            <Switch label="Desktop notifications" description="Timely updates while you are working. This preview does not request browser permission." checked={draft.push} onChange={() => change({ ...draft, push: !draft.push })} testId="desktop-setting" />
            <div className="flex flex-col gap-4 py-6 sm:flex-row sm:items-center sm:justify-between"><div><label htmlFor="digest" className="text-sm font-semibold">Digest frequency</label><p className="mt-1 text-sm leading-6 text-slate-600">Decide how often to catch up.</p></div><select id="digest" data-testid="digest-setting" value={draft.digest} onChange={event => change({ ...draft, digest: event.target.value })} className="min-h-11 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 sm:w-36"><option>Daily</option><option>Weekly</option><option>Never</option></select></div>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 bg-slate-50 px-6 py-4"><button type="button" data-testid="restore-defaults" onClick={reset} className="min-h-11 rounded-lg px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-200">Restore defaults</button><button type="submit" data-testid="save-preferences" disabled={!dirty} className="min-h-11 rounded-lg bg-indigo-700 px-5 py-3 text-sm font-medium text-white hover:bg-indigo-800 disabled:cursor-default disabled:bg-slate-200 disabled:text-slate-600">Save preferences</button></div>
        </form>
        <aside className="space-y-5"><section className="rounded-xl border border-slate-200 bg-white p-6"><h2 className="text-sm font-semibold">Current preferences</h2><dl className="mt-5 space-y-4 text-sm"><div className="flex justify-between gap-4"><dt className="text-slate-600">Email</dt><dd data-testid="saved-email" className="font-medium">{saved.email ? 'On' : 'Off'}</dd></div><div className="flex justify-between gap-4"><dt className="text-slate-600">Desktop</dt><dd data-testid="saved-desktop" className="font-medium">{saved.push ? 'On' : 'Off'}</dd></div><div className="flex justify-between gap-4"><dt className="text-slate-600">Digest</dt><dd data-testid="saved-digest" className="font-medium">{saved.digest}</dd></div></dl></section><p data-testid="draft-status" className="px-1 text-sm leading-6 text-slate-600">{dirty ? 'You have unsaved changes.' : 'Your preview is up to date.'}</p><p data-testid="save-status" role="status" className="px-1 text-sm leading-6 text-emerald-800">{message}</p><p className="border-t border-slate-200 pt-4 text-xs leading-5 text-slate-600">Local state only. Nothing is sent to a server, and preferences reset when this page reloads.</p></aside>
      </div>
    </main>
  </div>;
}
