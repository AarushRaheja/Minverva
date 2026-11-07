// src/frontend/Shell.tsx
import { PipelinePage } from "./PipelinePage";
import { DeepspeedZeroThreePage } from "./DeepspeedZeroThreePage";

export function Shell() {
  return (
    <div>
      <nav>
        <a href="/pipelines">Pipeline</a><br />
        <a href="/deepspeed_zero_threes">DeepspeedZeroThree</a><br />
      </nav>
      <main>
        <PipelinePage />
        <DeepspeedZeroThreePage />
      </main>
    </div>
  );
}
