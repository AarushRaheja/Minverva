// src/frontend/Shell.tsx
import { ChunkPage } from "./ChunkPage";
import { NodeRepairPage } from "./NodeRepairPage";

export function Shell() {
  return (
    <div>
      <nav>
        <a href="/chunks">Chunk</a><br />
        <a href="/node_repairs">NodeRepair</a><br />
      </nav>
      <main>
        <ChunkPage />
        <NodeRepairPage />
      </main>
    </div>
  );
}
