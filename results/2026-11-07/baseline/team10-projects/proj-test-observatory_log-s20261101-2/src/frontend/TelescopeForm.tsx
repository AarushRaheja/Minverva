// src/frontend/TelescopeForm.tsx
import { createTelescope } from "../network/telescope_client";

export function TelescopeForm() {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        createTelescope({ title: "new telescope" });
      }}
    >
      <input name="title" placeholder="Telescope title" />
      <button type="submit">Save</button>
    </form>
  );
}
