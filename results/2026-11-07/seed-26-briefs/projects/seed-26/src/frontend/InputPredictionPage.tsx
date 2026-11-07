// src/frontend/InputPredictionPage.tsx
import { useEffect, useState } from "react";

export const route = "/input_predictions";

type Row = { id: number; title: string };

export function InputPredictionPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/input_predictions")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>InputPrediction</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
