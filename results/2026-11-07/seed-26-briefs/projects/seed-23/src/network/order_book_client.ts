// src/network/order_book_client.ts
export type OrderBook = { id: number; title: string };

type NewOrderBook = Omit<OrderBook, "id">;

export async function listOrderBook(): Promise<OrderBook[]> {
  const res = await fetch("/api/order_books");
  return res.json();
}

export async function createOrderBook(payload: NewOrderBook): Promise<OrderBook> {
  const res = await fetch("/api/order_books", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
