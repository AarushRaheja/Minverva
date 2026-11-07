// src/frontend/Shell.tsx
import { DomainPage } from "./DomainPage";

export function Shell() {
  return (
    <div>
      <nav>
        <a href="/domains">Domain</a><br />
      </nav>
      <main>
        <DomainPage />
      </main>
    </div>
  );
}
