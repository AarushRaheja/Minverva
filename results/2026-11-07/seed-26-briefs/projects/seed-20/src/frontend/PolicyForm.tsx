// src/frontend/PolicyForm.tsx
import { createPolicy } from "../network/policy_client";

export function PolicyForm() {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        createPolicy({ title: "new policy" });
      }}
    >
      <input name="title" placeholder="Policy title" />
      <button type="submit">Save</button>
    </form>
  );
}
