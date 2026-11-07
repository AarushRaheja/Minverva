// src/frontend/StateCheckpointForm.tsx
import { createStateCheckpoint } from "../network/state_checkpoint_client";

export function StateCheckpointForm() {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        createStateCheckpoint({ title: "new state_checkpoint" });
      }}
    >
      <input name="title" placeholder="StateCheckpoint title" />
      <button type="submit">Save</button>
    </form>
  );
}
