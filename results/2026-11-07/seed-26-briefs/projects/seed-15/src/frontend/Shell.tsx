// src/frontend/Shell.tsx
import { EventPage } from "./EventPage";
import { RingBufferPage } from "./RingBufferPage";

export function Shell() {
  return (
    <div>
      <nav>
        <a href="/events">Event</a><br />
        <a href="/ring_buffers">RingBuffer</a><br />
      </nav>
      <main>
        <EventPage />
        <RingBufferPage />
      </main>
    </div>
  );
}
