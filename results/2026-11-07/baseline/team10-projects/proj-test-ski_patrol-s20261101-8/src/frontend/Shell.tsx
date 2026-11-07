// src/frontend/Shell.tsx
import { PatrollerPage } from "./PatrollerPage";

export function Shell() {
  return (
    <div>
      <nav>
        <a href="/patrollers">Patroller</a><br />
      </nav>
      <main>
        <PatrollerPage />
      </main>
    </div>
  );
}
