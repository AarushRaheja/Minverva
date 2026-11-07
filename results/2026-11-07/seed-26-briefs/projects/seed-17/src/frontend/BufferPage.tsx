// src/frontend/BufferPage.tsx
import { useEffect, useState } from "react";

export const route = "/buffers";

type Row = { id: number; title: string };

export function BufferPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/buffers")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>Buffer</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
