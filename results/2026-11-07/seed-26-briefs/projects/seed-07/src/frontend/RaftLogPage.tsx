// src/frontend/RaftLogPage.tsx
import { useEffect, useState } from "react";

export const route = "/raft_logs";

type Row = { id: number; title: string };

export function RaftLogPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/raft_logs")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>RaftLog</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
