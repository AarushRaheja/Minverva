// src/frontend/UserForm.tsx
import { createUser } from "../network/user_client";

export function UserForm() {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        createUser({ title: "new user" });
      }}
    >
      <input name="title" placeholder="User title" />
      <button type="submit">Save</button>
    </form>
  );
}
