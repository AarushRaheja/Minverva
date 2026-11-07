// src/frontend/DoughMixForm.tsx
import { createDoughMix } from "../network/dough_mix_client";

export function DoughMixForm() {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        createDoughMix({ title: "new dough_mix" });
      }}
    >
      <input name="title" placeholder="DoughMix title" />
      <button type="submit">Save</button>
    </form>
  );
}
