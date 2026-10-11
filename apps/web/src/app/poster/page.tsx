import { Suspense } from "react";
import { PosterScreen } from "./PosterScreen";

export const metadata = { title: "Report poster - DrainWatch" };

export default function PosterPage() {
  return (
    <Suspense>
      <PosterScreen />
    </Suspense>
  );
}
