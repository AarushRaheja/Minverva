// src/frontend/Shell.tsx
import { CometPage } from "./CometPage";
import { AstronomerPage } from "./AstronomerPage";
import { ObservationPage } from "./ObservationPage";
import { TelescopePage } from "./TelescopePage";

export function Shell() {
  return (
    <div>
      <nav>
        <a href="/comets">Comet</a><br />
        <a href="/astronomers">Astronomer</a><br />
        <a href="/observations">Observation</a><br />
        <a href="/telescopes">Telescope</a><br />
      </nav>
      <main>
        <CometPage />
        <AstronomerPage />
        <ObservationPage />
        <TelescopePage />
      </main>
    </div>
  );
}
