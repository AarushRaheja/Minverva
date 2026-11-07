// src/frontend/Shell.tsx
import { BufferPage } from "./BufferPage";
import { Vst3PluginPage } from "./Vst3PluginPage";

export function Shell() {
  return (
    <div>
      <nav>
        <a href="/buffers">Buffer</a><br />
        <a href="/vst3_plugins">Vst3Plugin</a><br />
      </nav>
      <main>
        <BufferPage />
        <Vst3PluginPage />
      </main>
    </div>
  );
}
