// src/frontend/BelayCheckForm.tsx
import { createBelayCheck } from "../network/belay_check_client";

export function BelayCheckForm() {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        createBelayCheck({ title: "new belay_check" });
      }}
    >
      <input name="title" placeholder="BelayCheck title" />
      <button type="submit">Save</button>
    </form>
  );
}
