// src/network/event_client.ts
export type Event = { id: number; title: string };

type NewEvent = Omit<Event, "id">;

export async function listEvent(): Promise<Event[]> {
  const res = await fetch("/api/events");
  return res.json();
}

export async function createEvent(payload: NewEvent): Promise<Event> {
  const res = await fetch("/api/events", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
