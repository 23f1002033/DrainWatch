import { Suspense } from "react";
import { QueueScreen } from "./QueueScreen";

export const metadata = { title: "Queue - DrainWatch Ops" };

export default function QueuePage() {
  return (
    <Suspense>
      <QueueScreen />
    </Suspense>
  );
}
