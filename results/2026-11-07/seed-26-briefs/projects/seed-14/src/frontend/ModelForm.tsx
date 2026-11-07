// src/frontend/ModelForm.tsx
import { createModel } from "../network/model_client";

export function ModelForm() {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        createModel({ title: "new model" });
      }}
    >
      <input name="title" placeholder="Model title" />
      <button type="submit">Save</button>
    </form>
  );
}
