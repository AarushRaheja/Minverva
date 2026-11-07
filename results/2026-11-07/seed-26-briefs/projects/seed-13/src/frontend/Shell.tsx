// src/frontend/Shell.tsx
import { FeaturePage } from "./FeaturePage";
import { SyncBackendPage } from "./SyncBackendPage";

export function Shell() {
  return (
    <div>
      <nav>
        <a href="/features">Feature</a><br />
        <a href="/sync_backends">SyncBackend</a><br />
      </nav>
      <main>
        <FeaturePage />
        <SyncBackendPage />
      </main>
    </div>
  );
}
