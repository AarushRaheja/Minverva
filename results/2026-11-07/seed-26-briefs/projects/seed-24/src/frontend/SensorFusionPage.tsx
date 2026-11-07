// src/frontend/SensorFusionPage.tsx
import { useEffect, useState } from "react";

export const route = "/sensor_fusions";

type Row = { id: number; title: string };

export function SensorFusionPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/sensor_fusions")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>SensorFusion</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
