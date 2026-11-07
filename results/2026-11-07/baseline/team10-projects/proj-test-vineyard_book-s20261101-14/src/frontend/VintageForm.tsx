// src/frontend/VintageForm.tsx
import { createVintage } from "../network/vintage_client";

export function VintageForm() {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        createVintage({ title: "new vintage" });
      }}
    >
      <input name="title" placeholder="Vintage title" />
      <button type="submit">Save</button>
    </form>
  );
}
