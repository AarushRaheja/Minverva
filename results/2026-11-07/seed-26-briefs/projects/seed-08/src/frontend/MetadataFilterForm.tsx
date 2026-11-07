// src/frontend/MetadataFilterForm.tsx
import { createMetadataFilter } from "../network/metadata_filter_client";

export function MetadataFilterForm() {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        createMetadataFilter({ title: "new MetadataFilter" });
      }}
    >
      <input name="title" placeholder="MetadataFilter title" />
      <button type="submit">Save</button>
    </form>
  );
}
