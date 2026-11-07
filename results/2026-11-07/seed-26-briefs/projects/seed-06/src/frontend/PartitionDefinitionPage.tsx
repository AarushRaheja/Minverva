// src/frontend/PartitionDefinitionPage.tsx
import { useEffect, useState } from "react";

export const route = "/partition_definitions";

type Row = { id: number; title: string };

export function PartitionDefinitionPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/partition_definitions")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>PartitionDefinition</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
