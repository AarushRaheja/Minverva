// src/frontend/Shell.tsx
import { BarrelPage } from "./BarrelPage";
import { VinePage } from "./VinePage";
import { CellarPage } from "./CellarPage";
import { VintagePage } from "./VintagePage";

export function Shell() {
  return (
    <div>
      <nav>
        <a href="/barrels">Barrel</a><br />
        <a href="/vines">Vine</a><br />
        <a href="/cellars">Cellar</a><br />
        <a href="/vintages">Vintage</a><br />
      </nav>
      <main>
        <BarrelPage />
        <VinePage />
        <CellarPage />
        <VintagePage />
      </main>
    </div>
  );
}
