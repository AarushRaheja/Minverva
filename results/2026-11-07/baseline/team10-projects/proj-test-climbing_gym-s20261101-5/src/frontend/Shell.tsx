// src/frontend/Shell.tsx
import { WallPage } from "./WallPage";
import { BelayCheckPage } from "./BelayCheckPage";

export function Shell() {
  return (
    <div>
      <nav>
        <a href="/walls">Wall</a><br />
        <a href="/belay_checks">BelayCheck</a><br />
      </nav>
      <main>
        <WallPage />
        <BelayCheckPage />
      </main>
    </div>
  );
}
