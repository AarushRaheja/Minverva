// src/frontend/Shell.tsx
import { DoughMixPage } from "./DoughMixPage";
import { BakerPage } from "./BakerPage";

export function Shell() {
  return (
    <div>
      <nav>
        <a href="/dough_mixes">DoughMix</a><br />
        <a href="/bakers">Baker</a><br />
      </nav>
      <main>
        <DoughMixPage />
        <BakerPage />
      </main>
    </div>
  );
}
