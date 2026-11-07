// src/frontend/ManuscriptForm.tsx
import { createManuscript } from "../network/manuscript_client";

export function ManuscriptForm() {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        createManuscript({ title: "new manuscript" });
      }}
    >
      <input name="title" placeholder="Manuscript title" />
      <button type="submit">Save</button>
    </form>
  );
}
