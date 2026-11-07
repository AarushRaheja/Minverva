// src/frontend/RecipeForm.tsx
import { createRecipe } from "../network/recipe_client";

export function RecipeForm() {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        createRecipe({ title: "new recipe" });
      }}
    >
      <input name="title" placeholder="Recipe title" />
      <button type="submit">Save</button>
    </form>
  );
}
