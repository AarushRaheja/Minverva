// src/frontend/RecipePage.tsx
import { useEffect, useState } from "react";

export const route = "/recipes";

type Row = { id: number; title: string };

export function RecipePage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/recipes")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>Recipe</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
