// src/frontend/DeepspeedZeroThreePage.tsx
import { useEffect, useState } from "react";

export const route = "/deepspeed_zero_threes";

type Row = { id: number; title: string };

export function DeepspeedZeroThreePage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/deepspeed_zero_threes")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>DeepspeedZeroThree</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
