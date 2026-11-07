// src/frontend/TableTownForm.tsx
import { createTableTown } from "../network/table_town_client";

export function TableTownForm() {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        createTableTown({ title: "new table_town" });
      }}
    >
      <input name="title" placeholder="TableTown title" />
      <button type="submit">Save</button>
    </form>
  );
}
