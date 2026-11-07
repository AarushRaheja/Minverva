// src/frontend/Shell.tsx
import { VulnerabilityReportPage } from "./VulnerabilityReportPage";
import { ContainerLayerPage } from "./ContainerLayerPage";

export function Shell() {
  return (
    <div>
      <nav>
        <a href="/vulnerability_reports">VulnerabilityReport</a><br />
        <a href="/container_layers">ContainerLayer</a><br />
      </nav>
      <main>
        <VulnerabilityReportPage />
        <ContainerLayerPage />
      </main>
    </div>
  );
}
