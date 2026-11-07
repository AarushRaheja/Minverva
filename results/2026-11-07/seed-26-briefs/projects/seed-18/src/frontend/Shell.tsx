// src/frontend/Shell.tsx
import { NvmeDevicePage } from "./NvmeDevicePage";
import { ThermalProfilePage } from "./ThermalProfilePage";

export function Shell() {
  return (
    <div>
      <nav>
        <a href="/nvme_devices">NvmeDevice</a><br />
        <a href="/thermal_profiles">ThermalProfile</a><br />
      </nav>
      <main>
        <NvmeDevicePage />
        <ThermalProfilePage />
      </main>
    </div>
  );
}
