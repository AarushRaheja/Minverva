// src/frontend/Shell.tsx
import { HarborPage } from "./HarborPage";
import { SailingPage } from "./SailingPage";
import { VesselPage } from "./VesselPage";

export function Shell() {
  return (
    <div>
      <nav>
        <a href="/harbors">Harbor</a><br />
        <a href="/sailings">Sailing</a><br />
        <a href="/vessels">Vessel</a><br />
      </nav>
      <main>
        <HarborPage />
        <SailingPage />
        <VesselPage />
      </main>
    </div>
  );
}
