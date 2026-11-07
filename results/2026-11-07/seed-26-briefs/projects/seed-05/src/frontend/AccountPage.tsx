// src/frontend/AccountPage.tsx
import { useEffect, useState } from "react";

export const route = "/accounts";

type Row = { id: number; title: string };

export function AccountPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/accounts")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>Account</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
