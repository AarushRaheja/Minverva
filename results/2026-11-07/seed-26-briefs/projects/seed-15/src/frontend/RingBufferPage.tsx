// src/frontend/RingBufferPage.tsx
import { useEffect, useState } from "react";

export const route = "/ring_buffers";

type Row = { id: number; title: string };

export function RingBufferPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/ring_buffers")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>RingBuffer</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
