// src/frontend/ChunkForm.tsx
import { createChunk } from "../network/chunk_client";

export function ChunkForm() {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        createChunk({ title: "new chunk" });
      }}
    >
      <input name="title" placeholder="Chunk title" />
      <button type="submit">Save</button>
    </form>
  );
}
