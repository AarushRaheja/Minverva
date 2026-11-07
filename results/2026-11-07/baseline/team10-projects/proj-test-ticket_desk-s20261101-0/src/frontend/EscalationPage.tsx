// src/frontend/EscalationPage.tsx
import { useEffect, useState } from "react";

export const route = "/escalations";

type Row = { id: number; title: string };

export function EscalationPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/escalations")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>Escalation</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
