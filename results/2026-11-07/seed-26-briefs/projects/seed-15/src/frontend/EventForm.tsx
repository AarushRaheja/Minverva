// src/frontend/EventForm.tsx
import { createEvent } from "../network/event_client";

export function EventForm() {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        createEvent({ title: "new event" });
      }}
    >
      <input name="title" placeholder="Event title" />
      <button type="submit">Save</button>
    </form>
  );
}
