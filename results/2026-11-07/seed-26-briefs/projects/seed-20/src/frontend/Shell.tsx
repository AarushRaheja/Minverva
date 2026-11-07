// src/frontend/Shell.tsx
import { PolicyPage } from "./PolicyPage";

export function Shell() {
  return (
    <div>
      <nav>
        <a href="/policys">Policy</a><br />
      </nav>
      <main>
        <PolicyPage />
      </main>
    </div>
  );
}
