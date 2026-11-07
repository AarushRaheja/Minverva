// src/frontend/EntryPage.tsx
import { useEffect, useState } from "react";

export const route = "/entrys";

type Row = { id: number; title: string };

export function EntryPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/entry")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>Entry</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
