// src/frontend/SyncBackendPage.tsx
import { useEffect, useState } from "react";

export const route = "/sync_backends";

type Row = { id: number; title: string };

export function SyncBackendPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/sync_backends")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>SyncBackend</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
