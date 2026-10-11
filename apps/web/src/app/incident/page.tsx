import { Suspense } from "react";
import { IncidentScreen } from "./IncidentScreen";

export const metadata = { title: "Incident - DrainWatch Ops" };

export default function IncidentPage() {
  return (
    <Suspense>
      <IncidentScreen />
    </Suspense>
  );
}
