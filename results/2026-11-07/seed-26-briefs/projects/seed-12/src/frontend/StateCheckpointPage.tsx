// src/frontend/StateCheckpointPage.tsx
import { useEffect, useState } from "react";

type Row = { id: number; title: string };

export const route = "/state_checkcases";

export function StateCheckpointPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/state_checkcases")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>StateCheckpoint</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
