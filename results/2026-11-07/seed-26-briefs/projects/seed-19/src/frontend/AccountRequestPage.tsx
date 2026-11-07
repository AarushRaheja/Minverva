// src/frontend/AccountRequestPage.tsx
import { useEffect, useState } from "react";

export const route = "/account_requests";

type Row = { id: number; title: string };

export function AccountRequestPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/account_requests")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>AccountRequest</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
