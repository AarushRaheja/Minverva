// src/frontend/TelemetryPage.tsx
import { useEffect, useState } from "react";

type Row = { id: number; title: string };

export const route = "/telemetry";

export function TelemetryPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/telemetry")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>Telemetry</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
