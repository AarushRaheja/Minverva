// src/frontend/PantryItemPage.tsx
import { useEffect, useState } from "react";

export const route = "/pantry_items";

type Row = { id: number; title: string };

export function PantryItemPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/pantry_items")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>PantryItem</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
