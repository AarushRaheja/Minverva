// src/frontend/Shell.tsx
import { StateCheckpointPage } from "./StateCheckpointPage";
import { ToolSandboxPage } from "./ToolSandboxPage";

export function Shell() {
  return (
    <div>
      <nav>
        <a href="/state_checkpoints">StateCheckpoint</a><br />
        <a href="/tool_sandboxes">ToolSandbox</a><br />
      </nav>
      <main>
        <StateCheckpointPage />
        <ToolSandboxPage />
      </main>
    </div>
  );
}
