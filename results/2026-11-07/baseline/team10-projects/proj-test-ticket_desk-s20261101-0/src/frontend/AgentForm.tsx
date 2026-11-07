// src/frontend/AgentForm.tsx
import { createAgent } from "../network/agent_client";

export function AgentForm() {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        createAgent({ title: "new agent" });
      }}
    >
      <input name="title" placeholder="Agent title" />
      <button type="submit">Save</button>
    </form>
  );
}
