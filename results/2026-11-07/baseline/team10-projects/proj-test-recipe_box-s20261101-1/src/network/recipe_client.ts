// src/network/recipe_client.ts
export type Recipe = { id: number; title: string };

type NewRecipe = Omit<Recipe, "id">;

export async function listRecipe(): Promise<Recipe[]> {
  const res = await fetch("/api/recipes");
  return res.json();
}

export async function createRecipe(payload: NewRecipe): Promise<Recipe> {
  const res = await fetch("/api/recipes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
