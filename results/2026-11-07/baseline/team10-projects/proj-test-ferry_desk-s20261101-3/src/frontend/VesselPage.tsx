// src/frontend/VesselPage.tsx
import { useEffect, useState } from "react";

export const route = "/vessels";

type Row = { id: number; title: string };

export function VesselPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/vessels")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>Vessel</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
