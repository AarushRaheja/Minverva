// src/frontend/Shell.tsx
import { TableTownPage } from "./TableTownPage";

export function Shell() {
  return (
    <div>
      <nav>
        <a href="/table_towns">TableTown</a><br />
      </nav>
      <main>
        <TableTownPage />
      </main>
    </div>
  );
}
