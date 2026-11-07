// src/frontend/NodeRepairPage.tsx
import { useEffect, useState } from "react";

type Row = { id: number; title: string };

export const route = "/node_repair";

export function NodeRepairPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/node_repairs")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>NodeRepair</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
