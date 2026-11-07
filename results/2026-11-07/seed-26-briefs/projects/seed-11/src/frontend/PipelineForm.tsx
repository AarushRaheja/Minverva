// src/frontend/PipelineForm.tsx
import { createPipeline } from "../network/pipeline_client";

export function PipelineForm() {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        createPipeline({ title: "new pipeline" });
      }}
    >
      <input name="title" placeholder="Pipeline title" />
      <button type="submit">Save</button>
    </form>
  );
}
