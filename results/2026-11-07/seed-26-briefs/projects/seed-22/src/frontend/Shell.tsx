// src/frontend/Shell.tsx
import { TelemetryPage } from "./TelemetryPage";

export function Shell() {
  return (
    <div>
      <nav>
        <a href="/telemetrys">Telemetry</a><br />
      </nav>
      <main>
        <TelemetryPage />
      </main>
    </div>
  );
}
