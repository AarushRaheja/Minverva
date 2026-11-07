// src/frontend/Shell.tsx
import { EntryPage } from "./EntryPage";

export function Shell() {
  return (
    <div>
      <nav>
        <a href="/entrys">Entry</a><br />
      </nav>
      <main>
        <EntryPage />
      </main>
    </div>
  );
}
