// src/frontend/CepTaskForm.tsx
import { createCepTask } from "../network/cep_task_client";

export function CepTaskForm() {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        createCepTask({ title: "new CEPTask" });
      }}
    >
      <input name="title" placeholder="CepTask title" />
      <button type="submit">Save</button>
    </form>
  );
}
