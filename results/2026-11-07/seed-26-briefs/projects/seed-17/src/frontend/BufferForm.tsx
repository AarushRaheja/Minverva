// src/frontend/BufferForm.tsx
import { createBuffer } from "../network/buffer_client";

export function BufferForm() {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        createBuffer({ title: "new buffer" });
      }}
    >
      <input name="title" placeholder="Buffer title" />
      <button type="submit">Save</button>
    </form>
  );
}
