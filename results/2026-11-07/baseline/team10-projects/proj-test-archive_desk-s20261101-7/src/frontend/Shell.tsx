// src/frontend/Shell.tsx
import { ManuscriptPage } from "./ManuscriptPage";

export function Shell() {
  return (
    <div>
      <nav>
        <a href="/manuscripts">Manuscript</a><br />
      </nav>
      <main>
        <ManuscriptPage />
      </main>
    </div>
  );
}
