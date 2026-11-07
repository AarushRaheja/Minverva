// src/frontend/Shell.tsx
import { SingerPage } from "./SingerPage";
import { ConcertPage } from "./ConcertPage";

export function Shell() {
  return (
    <div>
      <nav>
        <a href="/singers">Singer</a><br />
        <a href="/concerts">Concert</a><br />
      </nav>
      <main>
        <SingerPage />
        <ConcertPage />
      </main>
    </div>
  );
}
