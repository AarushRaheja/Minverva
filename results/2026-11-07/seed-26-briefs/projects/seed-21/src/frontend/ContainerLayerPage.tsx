// src/frontend/ContainerLayerPage.tsx
import { useEffect, useState } from "react";

export const route = "/container_layers";

type Row = { id: number; title: string };

export function ContainerLayerPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/container_layers")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>ContainerLayer</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
