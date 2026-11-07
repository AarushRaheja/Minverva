// src/frontend/EntryForm.tsx
import { createEntry } from "../network/entry_client";

export function EntryForm() {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        createEntry({ title: "new entry" });
      }}
    >
      <input name="title" placeholder="Entry title" />
      <button type="submit">Save</button>
    </form>
  );
}
