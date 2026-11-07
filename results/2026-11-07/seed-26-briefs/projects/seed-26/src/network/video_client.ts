// src/network/video_client.ts
export type Video = { id: number; title: string };

type NewVideo = Omit<Video, "id">;

export async function listVideo(): Promise<Video[]> {
  const res = await fetch("/api/videos");
  return res.json();
}

export async function createVideo(payload: NewVideo): Promise<Video> {
  const res = await fetch("/api/videos", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
