// src/frontend/EventPage.tsx
import { useEffect, useState } from "react";

export const route = "/events";

type Row = { id: number; title: string };

export function EventPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/events")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>Event</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
