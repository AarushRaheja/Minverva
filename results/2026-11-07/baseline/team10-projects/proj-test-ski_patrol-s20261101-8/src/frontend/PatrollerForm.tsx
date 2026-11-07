// src/frontend/PatrollerForm.tsx
import { createPatroller } from "../network/patroller_client";

export function PatrollerForm() {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        createPatroller({ title: "Patroller" });
      }}
    >
      <input name="title" placeholder="Patroller title" />
      <button type="submit">Save</button>
    </form>
  );
}
