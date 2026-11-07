// src/frontend/Shell.tsx
import { ModelPage } from "./ModelPage";

export function Shell() {
  return (
    <div>
      <nav>
        <a href="/models">Model</a><br />
      </nav>
      <main>
        <ModelPage />
      </main>
    </div>
  );
}
