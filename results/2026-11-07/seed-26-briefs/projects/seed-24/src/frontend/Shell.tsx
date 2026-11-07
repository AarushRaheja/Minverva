// src/frontend/Shell.tsx
import { DevicePage } from "./DevicePage";
import { SensorFusionPage } from "./SensorFusionPage";

export function Shell() {
  return (
    <div>
      <nav>
        <a href="/devices">Device</a><br />
        <a href="/sensor_fusions">SensorFusion</a><br />
      </nav>
      <main>
        <DevicePage />
        <SensorFusionPage />
      </main>
    </div>
  );
}
