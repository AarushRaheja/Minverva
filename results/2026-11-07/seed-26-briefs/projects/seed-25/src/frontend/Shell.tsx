// src/frontend/Shell.tsx
import { AudioTrackPage } from "./AudioTrackPage";

export function Shell() {
  return (
    <div>
      <nav>
        <a href="/audio_tracks">AudioTrack</a><br />
      </nav>
      <main>
        <AudioTrackPage />
      </main>
    </div>
  );
}
