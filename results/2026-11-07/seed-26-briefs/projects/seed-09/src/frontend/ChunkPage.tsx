// src/frontend/ChunkPage.tsx
import { useEffect, useState } from "react";

export const route = "/chunks";

type Row = { id: number; title: string };

export function ChunkPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/chunks")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>Chunk</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
