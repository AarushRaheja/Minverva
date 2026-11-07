// src/frontend/Shell.tsx
import { RecipePage } from "./RecipePage";
import { PantryItemPage } from "./PantryItemPage";
import { CookPage } from "./CookPage";

export function Shell() {
  return (
    <div>
      <nav>
        <a href="/recipes">Recipe</a><br />
        <a href="/pantry_items">PantryItem</a><br />
        <a href="/cooks">Cook</a><br />
      </nav>
      <main>
        <RecipePage />
        <PantryItemPage />
        <CookPage />
      </main>
    </div>
  );
}
