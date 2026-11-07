// src/frontend/AccountForm.tsx
import { createAccount } from "../network/account_client";

export function AccountForm() {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        createAccount({ title: "new account" });
      }}
    >
      <input name="title" placeholder="Account title" />
      <button type="submit">Save</button>
    </form>
  );
}
