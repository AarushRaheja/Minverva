// src/frontend/DomainForm.tsx
import { createDomain } from "../network/domain_client";

export function DomainForm() {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        createDomain({ title: "new domain" });
      }}
    >
      <input name="title" placeholder="Domain title" />
      <button type="submit">Save</button>
    </form>
  );
}
