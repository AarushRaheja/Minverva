// src/frontend/OrderBookPage.tsx
import { useEffect, useState } from "react";

export const route = "/order_books";

type Row = { id: number; title: string };

export function OrderBookPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/order_books")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>OrderBook</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
